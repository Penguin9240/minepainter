from __future__ import annotations

import json
from typing import Any, Optional

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QTextEdit,
    QLineEdit,
    QPushButton,
    QHBoxLayout,
)

from minepainter.app_settings import load_openai_api_key, load_debug_mode, load_openai_model
from minepainter.document import SkinDocument


_SYSTEM_PROMPT = (
    "You are MinePainter's armor assistant. "
    "You always return STRICT JSON with keys: "
    "\"message\" (string) and \"armor_state\" (object). "
    "\"armor_state\" must be JSON using MinePainter schema: "
    "version=2, format='minepainter_armor_state_v2', width=64, height=64, and areas. "
    "areas must contain sections: helmet, chestplate, arms, leggings, boots. "
    "Each area contains named faces and each face has 'uv' and 'pixels'. "
    "'pixels' must be a 2D grid with [r,g,b,a] per pixel (0..255). "
    "You must preserve exact per-face pixel matrix dimensions and valid UV arrays. "
    "Always include an armor_state. If no visual change is needed, return the input armor_state unchanged."
)


def _build_armor_reply_schema_from_state(armor_state_text: str) -> dict[str, Any]:
    """Build a strict JSON schema that locks armor face pixel dimensions to input state."""
    parsed = json.loads(armor_state_text)
    if not isinstance(parsed, dict):
        raise ValueError("Current armor_state must be a JSON object.")
    areas = parsed.get("areas")
    if not isinstance(areas, dict):
        raise ValueError("Current armor_state must include areas object.")

    pixel_schema: dict[str, Any] = {
        "type": "array",
        "minItems": 4,
        "maxItems": 4,
        "items": {"type": "integer", "minimum": 0, "maximum": 255},
    }

    area_properties: dict[str, Any] = {}
    area_required: list[str] = []
    for area_name, area_obj in areas.items():
        if not isinstance(area_name, str) or not isinstance(area_obj, dict):
            raise ValueError("armor_state areas must be an object of objects.")
        face_properties: dict[str, Any] = {}
        face_required: list[str] = []
        for face_name, face_obj in area_obj.items():
            if not isinstance(face_name, str) or not isinstance(face_obj, dict):
                raise ValueError("armor_state faces must be an object of objects.")
            uv = face_obj.get("uv")
            pixels = face_obj.get("pixels")
            if not isinstance(uv, list) or len(uv) != 4:
                raise ValueError(f"area '{area_name}' face '{face_name}' has invalid uv.")
            if not isinstance(pixels, list) or not pixels or not isinstance(pixels[0], list):
                raise ValueError(f"area '{area_name}' face '{face_name}' has invalid pixels.")
            h = len(pixels)
            w = len(pixels[0])
            if h <= 0 or w <= 0:
                raise ValueError(f"area '{area_name}' face '{face_name}' has empty pixels.")

            row_schema: dict[str, Any] = {
                "type": "array",
                "minItems": w,
                "maxItems": w,
                "items": pixel_schema,
            }
            face_properties[face_name] = {
                "type": "object",
                "additionalProperties": False,
                "required": ["uv", "pixels"],
                "properties": {
                    "uv": {
                        "type": "array",
                        "minItems": 4,
                        "maxItems": 4,
                        "items": {"type": "integer", "minimum": 0, "maximum": 63},
                    },
                    "pixels": {
                        "type": "array",
                        "minItems": h,
                        "maxItems": h,
                        "items": row_schema,
                    },
                },
            }
            face_required.append(face_name)

        area_properties[area_name] = {
            "type": "object",
            "additionalProperties": False,
            "required": face_required,
            "properties": face_properties,
        }
        area_required.append(area_name)

    armor_state_schema: dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "required": ["version", "format", "width", "height", "areas"],
        "properties": {
            "version": {"type": "integer", "enum": [2]},
            "format": {"type": "string", "enum": ["minepainter_armor_state_v2"]},
            "width": {"type": "integer", "enum": [64]},
            "height": {"type": "integer", "enum": [64]},
            "areas": {
                "type": "object",
                "additionalProperties": False,
                "required": area_required,
                "properties": area_properties,
            },
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["message", "armor_state"],
        "properties": {
            "message": {"type": "string"},
            "armor_state": armor_state_schema,
        },
    }


def _parse_payload(text: str) -> tuple[str, str]:
    payload = None
    try:
        payload = json.loads(text)
    except Exception:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            payload = json.loads(text[start:end + 1])
    if not isinstance(payload, dict):
        raise ValueError("Assistant did not return a JSON object.")
    message = str(payload.get("message", "")).strip()
    armor_state_obj = payload.get("armor_state", "")
    if not armor_state_obj:
        raise ValueError("Assistant reply is missing armor_state.")
    if not isinstance(armor_state_obj, dict):
        raise ValueError("Assistant armor_state must be a JSON object.")
    armor_state = json.dumps(armor_state_obj, separators=(",", ":"))
    if not message:
        message = "(No message)"
    return message, armor_state


def request_ai_armor_reply(
    api_key: str,
    model: str,
    user_text: str,
    armor_state_text: str,
    history_text: str,
    *,
    debug_mode: bool = False,
    max_attempts: int = 4,
) -> tuple[str, str]:
    """Request a valid assistant reply; retries with validation feedback."""
    try:
        from openai import OpenAI
    except Exception as e:
        raise RuntimeError(f"OpenAI SDK not available: {e}") from e

    def _debug_log(label: str, text: str) -> None:
        if not debug_mode:
            return
        print(f"[AI DEBUG] {label}:\n{text}\n", flush=True)

    client = OpenAI(api_key=api_key, max_retries=0, timeout=240)
    # Validate input state and build strict output schema from it.
    SkinDocument.decode_armor_state_text(armor_state_text)
    schema = _build_armor_reply_schema_from_state(armor_state_text)
    compact_state = json.dumps(json.loads(armor_state_text), separators=(",", ":"))
    base_user_payload = (
        "Conversation:\n"
        f"{history_text}\n\n"
        "User request:\n"
        f"{user_text}\n\n"
        "Current armor_state (JSON):\n"
        f"{compact_state}\n\n"
        "Return JSON only."
    )
    _debug_log("OUTBOUND_SYSTEM", _SYSTEM_PROMPT)

    last_err = "unknown"
    retry_suffix = ""
    for attempt in range(1, max_attempts + 1):
        user_payload = base_user_payload + retry_suffix
        _debug_log(f"OUTBOUND_USER_ATTEMPT_{attempt}", user_payload)
        response = client.responses.create(
            model=model,
            temperature=0,
            max_output_tokens=40000,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "minepainter_armor_reply",
                    "strict": True,
                    "schema": schema,
                }
            },
            input=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_payload},
            ],
        )

        text = getattr(response, "output_text", None)
        if not text:
            text = str(response)
        _debug_log(f"INBOUND_RAW_ATTEMPT_{attempt}", text)

        try:
            message, armor_state = _parse_payload(text)
            # Strong validation before returning.
            SkinDocument.decode_armor_state_text(armor_state)
            _debug_log("INBOUND_PARSED_MESSAGE", message)
            _debug_log("INBOUND_PARSED_ARMOR_STATE", armor_state)
            return message, armor_state
        except Exception as e:
            last_err = str(e)
            _debug_log(f"VALIDATION_ERROR_ATTEMPT_{attempt}", last_err)
            retry_suffix = (
                "\n\nYour previous response was invalid.\n"
                f"Validation error: {last_err}\n"
                "Fix and return JSON only.\n"
                "Requirements:\n"
                "1) armor_state must match the same schema as input.\n"
                "2) For every face, pixels matrix dimensions must exactly match its UV width/height.\n"
                "3) Keep all UV arrays valid.\n"
            )
            continue
    raise RuntimeError(f"Assistant failed to return valid armor state after {max_attempts} attempts: {last_err}")


class _AIRequestThread(QThread):
    finished_payload = Signal(str, str)  # message, armor_state
    failed = Signal(str)

    def __init__(
        self,
        api_key: str,
        model: str,
        user_text: str,
        armor_state_text: str,
        history_text: str,
        debug_mode: bool,
    ) -> None:
        super().__init__()
        self._api_key = api_key
        self._model = model
        self._user_text = user_text
        self._armor_state_text = armor_state_text
        self._history_text = history_text
        self._debug_mode = debug_mode

    def run(self) -> None:
        try:
            message, armor_state = request_ai_armor_reply(
                self._api_key,
                self._model,
                self._user_text,
                self._armor_state_text,
                self._history_text,
                debug_mode=self._debug_mode,
            )
            self.finished_payload.emit(message, armor_state)
        except Exception as e:
            self.failed.emit(str(e))


class AIChatPanel(QWidget):
    apply_armor_state_requested = Signal(str)
    status_message = Signal(str)

    def __init__(self, document: SkinDocument, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._document = document
        self._worker: Optional[_AIRequestThread] = None
        self._history_lines: list[str] = []
        self._build_ui()

    def _build_ui(self) -> None:
        self.setMinimumWidth(320)
        self.setMaximumWidth(420)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        title = QLabel("AI Assistant")
        layout.addWidget(title)

        self._chat_log = QTextEdit(self)
        self._chat_log.setReadOnly(True)
        self._chat_log.setPlaceholderText("Ask for armor edits. AI replies include a new armor state.")
        layout.addWidget(self._chat_log, stretch=1)

        row = QHBoxLayout()
        row.setSpacing(6)
        self._input = QLineEdit(self)
        self._input.setPlaceholderText("Describe the armor change...")
        self._input.returnPressed.connect(self._send)
        row.addWidget(self._input, stretch=1)
        self._send_btn = QPushButton("Send", self)
        self._send_btn.clicked.connect(self._send)
        row.addWidget(self._send_btn, stretch=0)
        layout.addLayout(row)

    def _append(self, role: str, text: str) -> None:
        safe = text.replace("<", "&lt;").replace(">", "&gt;")
        self._chat_log.append(f"<b>{role}:</b> {safe}")
        self._history_lines.append(f"{role}: {text}")
        if len(self._history_lines) > 16:
            self._history_lines = self._history_lines[-16:]

    def _set_busy(self, busy: bool) -> None:
        self._send_btn.setEnabled(not busy)
        self._input.setEnabled(not busy)
        if not busy:
            self._input.setFocus(Qt.FocusReason.OtherFocusReason)

    def _send(self) -> None:
        text = self._input.text().strip()
        if not text:
            return

        api_key = load_openai_api_key().strip()
        if not api_key:
            self._append("System", "Set your OpenAI API key in Settings first.")
            self.status_message.emit("Missing OpenAI API key.")
            return
        model = load_openai_model().strip()

        armor_state = self._document.get_armor_state_text()
        self._append("You", text)
        self._input.clear()
        self._set_busy(True)
        self.status_message.emit("AI assistant: generating reply...")

        history_text = "\n".join(self._history_lines)
        debug_mode = load_debug_mode()
        if debug_mode:
            print(f"[AI DEBUG] UI outbound user message:\n{text}\n", flush=True)
            print(f"[AI DEBUG] UI selected model:\n{model}\n", flush=True)
            print(f"[AI DEBUG] UI outbound armor_state:\n{armor_state}\n", flush=True)
        self._worker = _AIRequestThread(api_key, model, text, armor_state, history_text, debug_mode)
        self._worker.finished_payload.connect(self._on_result)
        self._worker.failed.connect(self._on_error)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

    def _on_result(self, message: str, armor_state: str) -> None:
        if load_debug_mode():
            print(f"[AI DEBUG] UI inbound assistant message:\n{message}\n", flush=True)
            print(f"[AI DEBUG] UI inbound armor_state:\n{armor_state}\n", flush=True)
        self._append("Assistant", message)
        self.apply_armor_state_requested.emit(armor_state)
        self.status_message.emit("AI assistant: armor updated.")

    def _on_error(self, error_text: str) -> None:
        self._append("System", f"AI error: {error_text}")
        self.status_message.emit("AI assistant request failed.")

    def _on_worker_finished(self) -> None:
        self._worker = None
        self._set_busy(False)
