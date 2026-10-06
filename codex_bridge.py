"""ChatGPT 로그인된 Codex CLI 실행. API 키를 사용하지 않는다."""
import os
import signal
import subprocess
import time

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage
import config


class CodexBridge(QThread):
    succeeded = Signal(str)
    failed = Signal(str)

    def __init__(self, sketch, result, log):
        super().__init__()
        self.sketch, self.result, self.log = sketch, result, log

    def run(self):
        process = None
        try:
            prompt = config.CODEX_PROMPT.format(result_path=self.result, sketch_path=self.sketch)
            command = [config.CODEX_BINARY, "-a", "never", "exec", "--skip-git-repo-check",
                       "--sandbox", "workspace-write", "-C", str(config.ROOT),
                       "--image", str(self.sketch), "--", prompt]
            with self.log.open("w", encoding="utf-8") as log:
                process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log,
                                           stderr=subprocess.STDOUT, start_new_session=True)
                started = time.monotonic()
                while process.poll() is None:
                    if self.isInterruptionRequested():
                        raise RuntimeError("생성이 취소되었습니다")
                    if time.monotonic() - started >= config.CODEX_TIMEOUT_SECONDS:
                        raise TimeoutError(f"생성 시간 초과 ({config.CODEX_TIMEOUT_SECONDS}초)")
                    self.msleep(100)
                if process.returncode:
                    raise RuntimeError(f"Codex 실행 실패 (코드 {process.returncode})")
                if not self.result.is_file() or QImage(str(self.result)).isNull():
                    raise RuntimeError("Codex가 유효한 결과 이미지를 저장하지 않았습니다")
            self.succeeded.emit(str(self.result))
        except Exception as exc:
            self.failed.emit(f"{exc}\n로그: {self.log}")
        finally:
            if process is not None and process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                except ProcessLookupError:
                    pass
