#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--xiaozhi-root", required=True)
    parser.add_argument("--plugin-dir", required=True)
    parser.add_argument("--wake-word", default="Robot")
    parser.add_argument("--input-device-name", default=None)
    parser.add_argument("--output-device-name", default=None)
    args = parser.parse_args()

    root = Path(args.xiaozhi_root).resolve()
    sys.path.insert(0, str(root))
    os.chdir(root)

    from src.audio_processing.keyword_converters import convert_wake_word
    from src.utils.config_manager import initialize_config
    from src.utils.resource_finder import get_user_keywords_path

    keyword_line, language, model_path = convert_wake_word(args.wake_word)
    keywords_path = get_user_keywords_path(language)
    keywords_path.parent.mkdir(parents=True, exist_ok=True)
    keywords_path.write_text(keyword_line + "\n", encoding="utf-8")

    config = initialize_config()
    updates = {
        "WAKE_WORD_OPTIONS.USE_WAKE_WORD": True,
        "WAKE_WORD_OPTIONS.WAKE_WORD": args.wake_word,
        "WAKE_WORD_OPTIONS.WAKE_WORD_LANG": language,
        "WAKE_WORD_OPTIONS.MODEL_PATH": model_path,
        "WAKE_WORD_OPTIONS.NUM_THREADS": 2,
        "WAKE_WORD_OPTIONS.MAX_ACTIVE_PATHS": 2,
        "WAKE_WORD_OPTIONS.KEYWORDS_SCORE": 2.0,
        "WAKE_WORD_OPTIONS.KEYWORDS_THRESHOLD": 0.25,
        "WAKE_WORD_OPTIONS.NUM_TRAILING_BLANKS": 1,
        "MCP_PLUGINS.ENABLED": True,
        "MCP_PLUGINS.DIR": str(Path(args.plugin_dir).resolve()),
        "AUDIO_DEVICES.opus_output_sample_rate": 24000,
        "AUDIO_DEVICES.frame_duration": 20,
        "CAMERA.backend": "picamera2",
        "LOGGING.LEVEL": "INFO",
    }
    if args.input_device_name:
        updates["AUDIO_DEVICES.input_device_name"] = args.input_device_name
    if args.output_device_name:
        updates["AUDIO_DEVICES.output_device_name"] = args.output_device_name
    if not config.update_configs(updates):
        raise RuntimeError("cannot update py-xiaozhi config")

    print(f"WAKE_WORD={args.wake_word}")
    print(f"WAKE_WORD_LANG={language}")
    print(f"WAKE_WORD_MODEL={model_path}")
    print(f"KEYWORDS_FILE={keywords_path}")
    print(f"KEYWORDS_LINE={keyword_line}")
    print(f"MCP_PLUGIN_DIR={Path(args.plugin_dir).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
