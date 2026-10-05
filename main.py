from __future__ import annotations

import json
import random
import re
import shutil
import threading
import time
import urllib.request
import zipfile
from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import Image, Plain
from astrbot.api.star import Context, Star, register

PLUGIN_DIR = Path(__file__).resolve().parent
IMG_DIR = PLUGIN_DIR / "img"
DATA_FILE = PLUGIN_DIR / "jrlp_data.json"
VALID_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
MS_PER_DAY = 86400

RELEASE_IMG_URLS = [
    "https://ghfast.top/https://github.com/Set-suei/galgame-LLM-jrlp/releases/download/v1.1.0/jrlp_img.zip",
    "https://github.com/Set-suei/galgame-LLM-jrlp/releases/download/v1.1.0/jrlp_img.zip",
]

PROMPT_JRLP = (
    "用户「{player}」抽今日老婆，抽到了「{wife_name}」。"
    "请你用你的人设和语气宣布这个结果并评价一句，可以吐槽、调侃、祝贺或吃醋，"
    "直接输出要说的话，不要加引号、不要解释、不要任何前缀。"
)
PROMPT_JRLP_AGAIN = (
    "用户「{player}」又来看今日老婆，今天已经抽过了，老婆是「{wife_name}」。"
    "请你用你的人设和语气提醒他/她今天的老婆还是这位，并点评一句，"
    "直接输出要说的话，不要加引号、不要解释、不要任何前缀。"
)
PROMPT_HLP = (
    "用户「{player}」换了老婆，新老婆是「{wife_name}」。"
    "请你用你的人设和语气宣布并评价一句，可以吐槽、调侃、祝贺或鄙视，"
    "直接输出要说的话，不要加引号、不要解释、不要任何前缀。"
)
PROMPT_HLP_LIMIT = (
    "用户「{player}」想换老婆，但今天换老婆次数已用完（每天最多{limit}次），今天的老婆还是「{wife_name}」。"
    "请你用你的人设和语气拒绝并调侃一句，"
    "直接输出要说的话，不要加引号、不要解释、不要任何前缀。"
)
PROMPT_MARRY = (
    "用户「{player}」和今天的老婆「{wife_name}」结婚了！"
    "请你用你的人设和语气宣布并送上祝福（或吐槽、吃醋），"
    "直接输出要说的话，不要加引号、不要解释、不要任何前缀。"
)
PROMPT_MARRIED_STATUS = (
    "用户「{player}」查看今日老婆，但他/她已经和「{wife_name}」结婚了，"
    "已经在一起{days}天，还剩{remain}天婚姻期。"
    "请你用你的人设和语气告诉他/她当前已婚状态并点评一句，"
    "直接输出要说的话，不要加引号、不要解释、不要任何前缀。"
)
PROMPT_DIVORCE = (
    "用户「{player}」和「{wife_name}」离婚了。"
    "请你用你的人设和语气宣布这件事并点评一句，可以安慰、吐槽或幸灾乐祸，"
    "直接输出要说的话，不要加引号、不要解释、不要任何前缀。"
)
PROMPT_NOT_MARRIED = (
    "用户「{player}」想离婚，但他/她根本没有结婚。"
    "请你用你的人设和语气告诉他/她这一点，可以调侃，"
    "直接输出要说的话，不要加引号、不要解释、不要任何前缀。"
)
PROMPT_NO_WIFE_MARRY = (
    "用户「{player}」想结婚，但他/她今天还没有抽老婆。"
    "请你用你的人设和语气提醒他/她先用 jrlp 抽一位今日老婆，"
    "直接输出要说的话，不要加引号、不要解释、不要任何前缀。"
)
PROMPT_HLP_BLOCKED = (
    "用户「{player}」想换老婆，但他/她已经结婚了，不能换老婆。"
    "请你用你的人设和语气拒绝，提醒他/她如需解除关系可先发 离婚，"
    "直接输出要说的话，不要加引号、不要解释、不要任何前缀。"
)
PROMPT_EMPTY = (
    "用户「{player}」想抽今日老婆，但图库为空抽不到。"
    "请你用你的人设和语气告诉他/她暂时抽不了老婆，"
    "直接输出要说的话，不要加引号、不要解释、不要任何前缀。"
)


@register(
    "astrbot_plugin_LLM_jrlp",
    "galgame-LLM-jrlp",
    "今日老婆插件移植版：随机抽一位 gal 角色作为今日老婆，支持换老婆、结婚、离婚，回复完全由 LLM 生成",
    "1.1.0",
)
class JrlpPlugin(Star):
    def __init__(self, context: Context, config: dict | None = None):
        super().__init__(context)
        self.config = config or {}
        self._data = {"version": 2, "users": {}}
        self._dl_lock = threading.Lock()
        self._dl_running = False
        self._dl_status = "idle"
        self._dl_progress = ""
        self._load()

        # 注意：不在 __init__ 自动拉起外网大文件下载线程，确保在沙箱加载、测试及市场解析时零开销纯净启动

    def _cfg(self, key: str, default):
        return self.config.get(key, default)

    @property
    def daily_limit(self) -> int:
        return int(self._cfg("daily_hlp_limit", 5))

    @property
    def marriage_duration(self) -> int:
        return int(self._cfg("marriage_duration", 7))

    # ─── 图库后台自动下载与解压 ──────────────────────────────────────────
    def _start_download_bg(self, force: bool = False) -> bool:
        with self._dl_lock:
            if self._dl_running:
                return False
            self._dl_running = True
            self._dl_status = "preparing"
            self._dl_progress = "准备中..."

        t = threading.Thread(
            target=self._download_worker,
            args=(force,),
            daemon=True,
            name="LLM-jrlp-img-downloader",
        )
        t.start()
        return True

    def _download_worker(self, force: bool = False):
        zip_tmp = PLUGIN_DIR / "jrlp_img_download.tmp"
        try:
            logger.info("[LLM-jrlp] 开始下载 Release 角色图库资源包 (约263MB)...")
            downloaded = False
            for url in RELEASE_IMG_URLS:
                host = url.split("/")[2]
                self._dl_status = f"downloading ({host})"
                self._dl_progress = "连接中..."
                try:
                    req = urllib.request.Request(
                        url,
                        headers={"User-Agent": "AstrBot-LLM-jrlp/1.1.0"},
                    )
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        total = int(resp.headers.get("Content-Length", 0))
                        chunk_size = 512 * 1024
                        received = 0
                        with open(zip_tmp, "wb") as out:
                            while True:
                                chunk = resp.read(chunk_size)
                                if not chunk:
                                    break
                                out.write(chunk)
                                received += len(chunk)
                                if total > 0:
                                    pct = int(received * 100 / total)
                                    mb_cur = received / (1024 * 1024)
                                    mb_tot = total / (1024 * 1024)
                                    self._dl_progress = f"{mb_cur:.1f}MB/{mb_tot:.1f}MB ({pct}%)"
                                else:
                                    mb_cur = received / (1024 * 1024)
                                    self._dl_progress = f"{mb_cur:.1f}MB"
                    downloaded = True
                    break
                except Exception as e:
                    logger.warning(f"[LLM-jrlp] 镜像源 {host} 下载失败: {e}")
                    if zip_tmp.exists():
                        try:
                            zip_tmp.unlink()
                        except Exception:
                            pass
                    continue

            if not downloaded or not zip_tmp.exists():
                self._dl_status = "failed"
                self._dl_progress = "下载失败，请检查网络后重试"
                logger.error("[LLM-jrlp] 角色图库下载失败：所有下载源均不可达")
                return

            self._dl_status = "extracting"
            self._dl_progress = "正在解压立绘..."
            IMG_DIR.mkdir(parents=True, exist_ok=True)
            extracted = 0

            with zipfile.ZipFile(zip_tmp, "r") as zf:
                for member in zf.infolist():
                    if member.is_dir():
                        continue
                    raw_name = Path(member.filename).name
                    if not raw_name:
                        continue
                    if not (member.flag_bits & 0x800):
                        for enc in ("gbk", "utf-8", "shift_jis"):
                            try:
                                raw_name = Path(member.filename.encode("cp437").decode(enc)).name
                                break
                            except Exception:
                                pass
                    suffix = Path(raw_name).suffix.lower()
                    if suffix not in VALID_EXTENSIONS:
                        continue
                    target = IMG_DIR / raw_name
                    with zf.open(member) as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    extracted += 1

            self._dl_status = "completed"
            self._dl_progress = f"完成，共解压 {extracted} 张角色立绘"
            logger.info(f"[LLM-jrlp] 角色图库自动配置完成，已加载 {extracted} 张立绘")
        except Exception as e:
            self._dl_status = "failed"
            self._dl_progress = f"处理异常: {e}"
            logger.error(f"[LLM-jrlp] 角色图库解压处理异常: {e}")
        finally:
            if zip_tmp.exists():
                try:
                    zip_tmp.unlink()
                except Exception:
                    pass
            with self._dl_lock:
                self._dl_running = False

    async def _download_command(self, event: AstrMessageEvent, force: bool = False):
        total = len(self._list_images())
        if self._dl_running:
            yield event.plain_result(
                f"【图库下载中】\n"
                f"状态: {self._dl_status}\n"
                f"进度: {self._dl_progress}\n"
                f"下载完成后将自动生效，无需重启 Bot。"
            )
            return

        if total > 0 and not force:
            yield event.plain_result(
                f"【图库已就绪】\n"
                f"当前本地已有 {total} 张角色立绘，可正常使用。\n"
                f"如需强制重新下载，请发送「jrlp force-download」。"
            )
            return

        started = self._start_download_bg(force=force)
        if started:
            yield event.plain_result(
                "【开始下载图库】\n"
                "已启动后台下载任务（资源包约 263MB）。\n"
                "支持国内镜像加速，下载与解压完成后将自动载入，无需重启。\n"
                "可随时发送「jrlp download」查看实时进度。"
            )
        else:
            yield event.plain_result("后台已有下载任务正在运行中，请稍候查看。")

    # ─── 持久化 ────────────────────────────────────────────────────────
    def _load(self):
        try:
            if DATA_FILE.is_file():
                raw = json.loads(DATA_FILE.read_text(encoding="utf-8"))
                if isinstance(raw, dict) and isinstance(raw.get("users"), dict):
                    self._data = raw
        except Exception as e:
            logger.error(f"[LLM-jrlp] 数据加载失败，重置为空: {e}")
            self._data = {"version": 2, "users": {}}

    def _save(self):
        try:
            DATA_FILE.write_text(
                json.dumps(self._data, ensure_ascii=False), encoding="utf-8"
            )
        except Exception as e:
            logger.error(f"[LLM-jrlp] 数据保存失败: {e}")

    def _user(self, uid: str) -> dict:
        users = self._data["users"]
        if uid not in users:
            users[uid] = {
                "lastDayId": "",
                "dailyCount": 0,
                "wife": None,
                "marriage": None,
            }
        return users[uid]

    # ─── 日期 / 婚姻状态 ───────────────────────────────────────────────
    @staticmethod
    def _day_id() -> str:
        return time.strftime("%Y-%m-%d")

    def _reset_if_new_day(self, uid: str):
        user = self._user(uid)
        today = self._day_id()
        if user["lastDayId"] != today:
            user["lastDayId"] = today
            user["dailyCount"] = 0
            user["wife"] = None
            self._save()

    def _check_marriage_expiry(self, uid: str):
        user = self._user(uid)
        m = user.get("marriage")
        if not m:
            return
        elapsed_days = int((time.time() - m["startTimestamp"] / 1000) / MS_PER_DAY)
        if self.marriage_duration - elapsed_days <= 0:
            user["marriage"] = None
            self._save()

    @staticmethod
    def _married_days(marriage: dict) -> int:
        elapsed = time.time() - marriage["startTimestamp"] / 1000
        return max(1, int(elapsed / MS_PER_DAY))

    def _remaining_days(self, marriage: dict) -> int:
        elapsed = time.time() - marriage["startTimestamp"] / 1000
        return max(0, self.marriage_duration - int(elapsed / MS_PER_DAY))

    # ─── 角色图库 ──────────────────────────────────────────────────────
    def _list_images(self) -> list[Path]:
        if not IMG_DIR.is_dir():
            return []
        return [
            p
            for p in IMG_DIR.rglob("*")
            if p.is_file() and p.suffix.lower() in VALID_EXTENSIONS
        ]

    def _random_character(self) -> dict | None:
        images = self._list_images()
        if not images:
            return None
        for _ in range(3):
            chosen = random.choice(images)
            if chosen.is_file():
                return {"name": chosen.stem, "path": str(chosen)}
        return None

    def _image_path_by_name(self, name: str) -> str | None:
        for p in self._list_images():
            if p.stem == name:
                return str(p)
        return None

    # ─── 当前会话人设 ──────────────────────────────────────────────────
    @staticmethod
    async def _maybe_await(value):
        """兼容同步/异步方法：若返回可等待对象则 await。"""
        if hasattr(value, "__await__"):
            return await value
        return value

    @staticmethod
    def _extract_persona_prompt(obj) -> str:
        """兼容 dict 与对象两种人格表示，取出 system prompt 文本。"""
        if obj is None:
            return ""
        try:
            if hasattr(obj, "get"):
                for key in ("prompt", "system_prompt"):
                    try:
                        v = obj.get(key)
                    except Exception:
                        v = None
                    if v:
                        return v
        except Exception:
            pass
        for attr in ("system_prompt", "prompt"):
            try:
                v = getattr(obj, attr, None)
            except Exception:
                v = None
            if v:
                return v
        return ""

    @staticmethod
    def _persona_name_of(obj) -> str:
        """兼容 dict 与对象两种人格表示，取人格 id/name。"""
        if obj is None:
            return ""
        try:
            if hasattr(obj, "get"):
                for key in ("persona_id", "name", "id"):
                    try:
                        v = obj.get(key)
                    except Exception:
                        v = None
                    if v:
                        return str(v)
        except Exception:
            pass
        for attr in ("persona_id", "name", "id"):
            try:
                v = getattr(obj, attr, None)
            except Exception:
                v = None
            if v:
                return str(v)
        return ""

    async def _resolve_persona_prompt(self, pm, persona_id, umo: str) -> str:
        """跨 AstrBot 版本解析人格 system prompt；解析不到返回 ''。"""
        if persona_id and persona_id not in ("default", "[%None]"):
            # 1) 按人格 id 查询（兼容不同版本的 PersonaManager 方法名）
            for method_name in (
                "get_persona_v3_by_id",
                "get_persona_by_id",
                "get_persona",
            ):
                fn = getattr(pm, method_name, None)
                if fn is None:
                    continue
                try:
                    persona = await self._maybe_await(fn(persona_id))
                    prompt = self._extract_persona_prompt(persona)
                    if prompt:
                        return prompt
                except Exception:
                    continue
            # 2) 扫描 PersonaManager 内存缓存的人格列表
            for attr_name in ("personas_v3", "personas"):
                for persona in getattr(pm, attr_name, None) or []:
                    if self._persona_name_of(persona) == persona_id:
                        prompt = self._extract_persona_prompt(persona)
                        if prompt:
                            return prompt
            # 3) 从数据库全量扫描（异步/同步方法皆可）
            get_all = getattr(pm, "get_all_personas", None)
            if get_all is not None:
                try:
                    for persona in await self._maybe_await(get_all()):
                        if self._persona_name_of(persona) == persona_id:
                            prompt = self._extract_persona_prompt(persona)
                            if prompt:
                                return prompt
                except Exception:
                    pass
        # 4) 未显式指定人格时，取会话默认人格（与 AstrBot 聊天行为一致）
        if persona_id is None or persona_id in ("default", "[%None]"):
            fn = getattr(pm, "get_default_persona_v3", None)
            if fn is not None:
                try:
                    persona = await self._maybe_await(fn(umo))
                    prompt = self._extract_persona_prompt(persona)
                    if prompt:
                        return prompt
                except Exception:
                    pass
        # 5) 兜底：PersonaManager 记录的默认人格对象
        for attr_name in ("selected_default_persona_v3", "selected_default_persona"):
            prompt = self._extract_persona_prompt(getattr(pm, attr_name, None))
            if prompt:
                return prompt
        return ""

    async def _get_persona_prompt(self, event: AstrMessageEvent) -> str:
        """取当前会话生效的人格 system prompt（含默认人格）；解析不到返回 ''。"""
        umo = event.unified_msg_origin
        persona_id = None
        cm = getattr(self.context, "conversation_manager", None)
        if cm is not None:
            try:
                cid = await cm.get_curr_conversation_id(umo)
                if cid:
                    conv = await cm.get_conversation(umo, cid)
                    persona_id = getattr(conv, "persona_id", None)
            except Exception as e:
                logger.debug(f"[LLM-jrlp] 读取会话人格失败: {e}")
        if not persona_id or persona_id == "[%None]":
            persona_id = None
            try:
                cfg = self.context.persona_manager.acm.get_conf(umo)
                persona_id = cfg.get("provider_settings", {}).get(
                    "default_personality", "default"
                )
            except Exception:
                persona_id = "default"
        pm = getattr(self.context, "persona_manager", None)
        if pm is None:
            return ""
        try:
            return await self._resolve_persona_prompt(pm, persona_id, umo)
        except Exception as e:
            logger.debug(f"[LLM-jrlp] 读取人格 prompt 失败: {e}")
        return ""

    # ─── GENIE 语音接入 ───────────────────────────────────────────────
    def _is_genie_active(self, event: AstrMessageEvent) -> bool:
        """检查当前会话与环境下是否启用了语音插件。"""
        genie = self._find_genie()
        if genie is None:
            return False
        try:
            sid = str(getattr(event, "unified_msg_origin", None) or "default")
            if hasattr(genie, "data_manager") and hasattr(genie.data_manager, "is_tts_disabled"):
                if genie.data_manager.is_tts_disabled(sid):
                    return False
            if hasattr(genie, "_should_auto_tts"):
                if not genie._should_auto_tts(event, sid):
                    return False
            if hasattr(genie, "prompt_injection_enabled") and not genie.prompt_injection_enabled:
                return False
            return True
        except Exception:
            return False

    @staticmethod
    def _clean_single_chinese(text: str) -> str:
        """在未启用语音插件时，清洗提取单语言（纯中文），剥离日文与标签。"""
        if not text:
            return ""
        # 优先提取 <zh>...</zh>
        zh_matches = re.findall(r"<zh>(.*?)</zh>", text, re.DOTALL | re.IGNORECASE)
        if zh_matches:
            return "\n".join(m.strip() for m in zh_matches if m.strip())
        # 移除 <ja>...</ja> 及其内容
        cleaned = re.sub(r"<ja>[\s\S]*?</ja>", "", text, flags=re.IGNORECASE)
        cleaned = re.sub(r"<think>[\s\S]*?</think>", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"<thought>[\s\S]*?</thought>", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"</?[A-Za-z_][^<>]*>", "", cleaned).strip()
        # 逐行过滤掉纯假名日文行
        lines = []
        kana_re = re.compile(r"[぀-ゟ゠-ヿ]")
        cjk_re = re.compile(r"[一-鿿]")
        for line in cleaned.splitlines():
            line_s = line.strip()
            if not line_s:
                continue
            if kana_re.search(line_s) and not cjk_re.search(line_s):
                continue
            lines.append(line_s)
        res = "\n".join(lines).strip()
        return res or cleaned

    def _find_genie(self):
        """查找已加载且激活的 genie 语音插件实例。

        未安装 / 未启用 / 接口不可用时返回 None，调用方应退回原有行为。
        """
        try:
            get_all = getattr(self.context, "get_all_stars", None)
            if get_all is None:
                return None
            for md in get_all():
                if not getattr(md, "activated", True):
                    continue
                if not getattr(md, "star_cls", None):
                    continue
                name = (getattr(md, "name", "") or "").lower()
                root = (getattr(md, "root_dir_name", "") or "").lower()
                if name in ("genie", "astrbot_plugin_genie") or root in (
                    "genie",
                    "astrbot_plugin_genie",
                ):
                    return md.star_cls
        except Exception as e:
            logger.warning(f"[LLM-jrlp] 查找 genie 插件失败: {e}")
        return None

    # ─── LLM 评价 ──────────────────────────────────────────────────────
    async def _llm(self, event: AstrMessageEvent, prompt: str, fallback: str) -> str:
        """调用 LLM 生成回复。
        开语音插件时：注入双语要求并通过 voice_plugin_reply 协同发送日文语音；
        没开语音插件时：使用普通中文 Prompt，并严格输出单语言中文，不输出日文标签与语音。
        """
        try:
            provider = self.context.get_using_provider(event.unified_msg_origin)
            if provider is not None:
                persona_prompt = await self._get_persona_prompt(event)
                is_voice_active = self._is_genie_active(event)
                genie = self._find_genie() if is_voice_active else None

                llm_prompt = prompt
                if is_voice_active and genie is not None:
                    try:
                        hint = genie.build_prompt_injection_hint() or ""
                        if hint:
                            persona_prompt = f"{persona_prompt or ''}{hint}"
                        llm_prompt = (
                            f"{prompt}\n"
                            "【特别输出规范】：请务必同时严格输出 <zh>中文回复</zh> 与 <ja>日本語の返信</ja> 两种语言标签，"
                            "<ja> 标签内必须为地道日语对白（严禁英文、中文或动作括号）。"
                        )
                    except Exception as e:
                        logger.warning(f"[LLM-jrlp] 读取 genie 双语注入提示失败: {e}")

                resp = await provider.text_chat(
                    prompt=llm_prompt,
                    session_id=None,
                    contexts=[],
                    image_urls=[],
                    system_prompt=persona_prompt or None,
                )
                text = (resp.completion_text or "").strip()
                if text:
                    if is_voice_active and genie is not None:
                        try:
                            voice_plugin_reply = getattr(genie, "voice_plugin_reply", None)
                            if voice_plugin_reply:
                                display = await voice_plugin_reply(event, text)
                                if display:
                                    return display
                        except Exception as e:
                            logger.warning(f"[LLM-jrlp] genie 语音接入失败，按单语言展示: {e}")
                    # 没开语音插件时，严格过滤日文与标签，输出单语言中文
                    return self._clean_single_chinese(text)
        except Exception as e:
            logger.error(f"[LLM-jrlp] LLM 调用失败: {e}")

        if fallback:
            if self._is_genie_active(event):
                genie = self._find_genie()
                if genie is not None:
                    try:
                        voice_plugin_reply = getattr(genie, "voice_plugin_reply", None)
                        if callable(voice_plugin_reply):
                            disp = await voice_plugin_reply(event, fallback)
                            if disp:
                                return disp
                    except Exception as e:
                        logger.warning(f"[LLM-jrlp] fallback 语音接入失败: {e}")
            return self._clean_single_chinese(fallback)

        return fallback

    @staticmethod
    def _chain(text: str, image_path: str | None):
        chain = []
        if image_path:
            chain.append(Image.fromFileSystem(image_path))
        if text:
            chain.append(Plain(text))
        return chain

    # ─── 指令（带前缀）─────────────────────────────────────────────────
    @staticmethod
    def _claim_event(event: AstrMessageEvent) -> bool:
        """同一条消息可能同时命中「标准指令」与「无前缀监听」（私聊 / @ /
        带唤醒前缀时两者都会被 AstrBot 激活并依次执行）。

        事件级标记保证同一条消息只被处理一次，避免指令被执行两次、
        大模型连续回复两条内容。
        """
        if getattr(event, "_jrlp_claimed", False):
            return True
        event._jrlp_claimed = True
        return False

    @filter.command("jrlp", alias={"今日老婆"})
    async def jrlp(self, event: AstrMessageEvent):
        """今日老婆。子指令：status / 结婚 / 离婚"""
        if self._claim_event(event):
            return
        arg = event.message_str.strip().split(maxsplit=1)
        sub = arg[1].strip() if len(arg) > 1 else ""
        if sub == "status":
            async for r in self._status(event):
                yield r
            return
        if sub in ("结婚", "marry"):
            async for r in self._marry(event):
                yield r
            return
        if sub in ("离婚", "divorce"):
            async for r in self._divorce(event):
                yield r
            return
        if sub in ("download", "下载", "下载图库", "图库下载"):
            async for r in self._download_command(event, force=False):
                yield r
            return
        if sub in ("force-download", "强制下载"):
            async for r in self._download_command(event, force=True):
                yield r
            return
        async for r in self._draw(event):
            yield r

    @filter.command("hlp", alias={"换老婆"})
    async def hlp(self, event: AstrMessageEvent):
        """换老婆（每日有限次数）"""
        if self._claim_event(event):
            return
        async for r in self._redraw(event):
            yield r

    # ─── 无前缀触发 ────────────────────────────────────────────────────
    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_plain_message(self, event: AstrMessageEvent):
        # 标准指令若已处理（或将要处理）本消息，这里不再兜底，避免重复回复
        if self._claim_event(event):
            return
        text = event.message_str.strip()
        low = text.lower()
        if low in ("jrlp", "今日老婆"):
            async for r in self._draw(event):
                yield r
        elif low in ("hlp", "换老婆"):
            async for r in self._redraw(event):
                yield r
        elif low in ("jrlp status", "今日老婆 status", "jrlp状态", "今日老婆状态"):
            async for r in self._status(event):
                yield r
        elif low in ("jrlp 结婚", "今日老婆 结婚", "结婚"):
            async for r in self._marry(event):
                yield r
        elif low in ("jrlp 离婚", "今日老婆 离婚", "离婚"):
            async for r in self._divorce(event):
                yield r
        elif low in ("jrlp download", "今日老婆 download", "下载图库", "jrlp下载图库"):
            async for r in self._download_command(event, force=False):
                yield r

    # ─── 核心逻辑 ──────────────────────────────────────────────────────
    async def _draw(self, event: AstrMessageEvent):
        uid = event.get_sender_id()
        name = event.get_sender_name() or "你"
        self._reset_if_new_day(uid)
        self._check_marriage_expiry(uid)
        user = self._user(uid)

        marriage = user.get("marriage")
        if marriage:
            wife = marriage["wife"]
            text = await self._llm(
                event,
                PROMPT_MARRIED_STATUS.format(
                    player=name,
                    wife_name=wife["name"],
                    days=self._married_days(marriage),
                    remain=self._remaining_days(marriage),
                ),
                f"{name}与{wife['name']}已经幸福地生活了{self._married_days(marriage)}天\n(剩余{self._remaining_days(marriage)}天)",
            )
            yield event.chain_result(
                self._chain(text, self._image_path_by_name(wife["name"]))
            )
            return

        if user["dailyCount"] > 0 and user.get("wife"):
            wife = user["wife"]
            text = await self._llm(
                event,
                PROMPT_JRLP_AGAIN.format(player=name, wife_name=wife["name"]),
                f"{name}今天的老婆是{wife['name']}",
            )
            yield event.chain_result(
                self._chain(text, self._image_path_by_name(wife["name"]))
            )
            return

        chara = self._random_character()
        if not chara:
            if self._dl_running:
                yield event.plain_result(
                    f"【角色图库准备中】\n"
                    f"检测到本地图库正在下载/解压中（{self._dl_progress}）。\n"
                    f"请稍等片刻，下载完成后即可抽取今日老婆~"
                )
            else:
                self._start_download_bg()
                text = await self._llm(
                    event,
                    PROMPT_EMPTY.format(player=name),
                    "获取老婆失败，本地角色图库为空。已自动开启后台下载任务（约263MB），稍候即可抽取。",
                )
                yield event.plain_result(text)
            return

        user["wife"] = {"name": chara["name"]}
        user["dailyCount"] += 1
        self._save()

        text = await self._llm(
            event,
            PROMPT_JRLP.format(player=name, wife_name=chara["name"]),
            f"{name}今天的老婆是{chara['name']}",
        )
        yield event.chain_result(self._chain(text, chara["path"]))

    async def _redraw(self, event: AstrMessageEvent):
        uid = event.get_sender_id()
        name = event.get_sender_name() or "你"
        self._reset_if_new_day(uid)
        self._check_marriage_expiry(uid)
        user = self._user(uid)

        if user.get("marriage"):
            text = await self._llm(
                event,
                PROMPT_HLP_BLOCKED.format(player=name),
                "你已经结婚了，不能换老婆哦！\n如需解除关系请先发 离婚",
            )
            yield event.plain_result(text)
            return

        if user["dailyCount"] == 0:
            text = await self._llm(
                event,
                PROMPT_NO_WIFE_MARRY.format(player=name),
                "你还没有今日老婆，先发 jrlp 获取一位吧",
            )
            yield event.plain_result(text)
            return

        if user["dailyCount"] >= self.daily_limit:
            wife = user.get("wife")
            wife_name = wife["name"] if wife else "神秘角色"
            text = await self._llm(
                event,
                PROMPT_HLP_LIMIT.format(
                    player=name, wife_name=wife_name, limit=self.daily_limit
                ),
                f"{name}今天的老婆是{wife_name}\n(每天最多换{self.daily_limit}次老婆哦)",
            )
            img = self._image_path_by_name(wife_name) if wife else None
            yield event.chain_result(self._chain(text, img))
            return

        chara = self._random_character()
        if not chara:
            if self._dl_running:
                yield event.plain_result(
                    f"【角色图库准备中】\n"
                    f"检测到本地图库正在下载/解压中（{self._dl_progress}）。\n"
                    f"请稍等片刻，下载完成后即可抽取今日老婆~"
                )
            else:
                self._start_download_bg()
                text = await self._llm(
                    event,
                    PROMPT_EMPTY.format(player=name),
                    "获取老婆失败，本地角色图库为空。已自动开启后台下载任务（约263MB），稍候即可抽取。",
                )
                yield event.plain_result(text)
            return

        user["wife"] = {"name": chara["name"]}
        user["dailyCount"] += 1
        self._save()

        text = await self._llm(
            event,
            PROMPT_HLP.format(player=name, wife_name=chara["name"]),
            f"{name}的新老婆是{chara['name']}",
        )
        yield event.chain_result(self._chain(text, chara["path"]))

    async def _marry(self, event: AstrMessageEvent):
        uid = event.get_sender_id()
        name = event.get_sender_name() or "你"
        self._reset_if_new_day(uid)
        self._check_marriage_expiry(uid)
        user = self._user(uid)

        marriage = user.get("marriage")
        if marriage:
            wife = marriage["wife"]
            text = await self._llm(
                event,
                PROMPT_MARRIED_STATUS.format(
                    player=name,
                    wife_name=wife["name"],
                    days=self._married_days(marriage),
                    remain=self._remaining_days(marriage),
                ),
                f"{name}与{wife['name']}已经幸福地生活了{self._married_days(marriage)}天",
            )
            yield event.chain_result(
                self._chain(text, self._image_path_by_name(wife["name"]))
            )
            return

        wife = user.get("wife")
        if not wife:
            text = await self._llm(
                event,
                PROMPT_NO_WIFE_MARRY.format(player=name),
                "你还没有今日老婆，先发 jrlp 获取一位吧",
            )
            yield event.plain_result(text)
            return

        user["marriage"] = {
            "wife": {"name": wife["name"]},
            "startTimestamp": int(time.time() * 1000),
        }
        self._save()

        text = await self._llm(
            event,
            PROMPT_MARRY.format(player=name, wife_name=wife["name"]),
            f"恭喜{name}与{wife['name']}喜结连理！",
        )
        yield event.chain_result(
            self._chain(text, self._image_path_by_name(wife["name"]))
        )

    async def _divorce(self, event: AstrMessageEvent):
        uid = event.get_sender_id()
        name = event.get_sender_name() or "你"
        self._reset_if_new_day(uid)
        self._check_marriage_expiry(uid)
        user = self._user(uid)

        marriage = user.get("marriage")
        if not marriage:
            text = await self._llm(
                event,
                PROMPT_NOT_MARRIED.format(player=name),
                "你还没有结婚哦",
            )
            yield event.plain_result(text)
            return

        wife_name = marriage["wife"]["name"]
        user["marriage"] = None
        self._save()

        text = await self._llm(
            event,
            PROMPT_DIVORCE.format(player=name, wife_name=wife_name),
            f"{name}与{wife_name}的缘分走到了尽头...",
        )
        yield event.plain_result(text)

    async def _status(self, event: AstrMessageEvent):
        total = len(self._list_images())
        married = sum(1 for u in self._data["users"].values() if u.get("marriage"))
        dl_info = ""
        if self._dl_running:
            dl_info = f"\n图库下载进度: {self._dl_status} - {self._dl_progress}"
        elif total == 0:
            dl_info = "\n图库状态: 未就绪（发「jrlp download」开始下载）"

        yield event.plain_result(
            "服务状态: Available\n"
            f"角色图库数量: {total}{dl_info}\n"
            f"当前已婚用户: {married}\n"
            f"每日换老婆上限: {self.daily_limit}\n"
            f"婚姻维持天数: {self.marriage_duration}"
        )