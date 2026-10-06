from pathlib import Path

ROOT = Path(__file__).parent
MODEL_PATH = str(ROOT / "models" / "hand_landmarker.task")

# 카메라
CAMERA_INDEX = 0
CAMERA_WIDTH = 1280
CAMERA_HEIGHT = 720
CAMERA_FPS = 30

# MediaPipe
NUM_HANDS = 2
MIN_DETECTION_CONF = 0.6
MIN_PRESENCE_CONF = 0.5
MIN_TRACKING_CONF = 0.5

# 카메라 프레임 중앙의 이 비율 영역을 화면 전체에 매핑
MAP_REGION_W = 0.7
MAP_REGION_H = 0.7

# 검지 좌표 EMA (1에 가까울수록 반응 빠름, 떨림 많음)
CURSOR_EMA_ALPHA = 0.45

# 화면
PREVIEW_SIZE = (240, 135)
PREVIEW_MARGIN = 16
CURSOR_RADIUS = 9
DEFAULT_COLOR = "#000000"

# 제스처 / 획 (화면 좌표는 Qt 논리 픽셀)
FINGER_EXTEND_RATIO = 1.15
GESTURE_DEBOUNCE_FRAMES = 4
DRAW_START_FRAMES = 1
DRAW_INDEX_ENTER_RATIO = 1.04
DRAW_INDEX_HOLD_RATIO = 0.98
DRAW_INDEX_MIN_ANGLE = 145  # PIP가 곧게 펴졌다면 거리 비율이 작아도 허용
STROKE_THICKNESS = 6
STROKE_MIN_DISTANCE = 2.5

PALETTE_COLORS = ("#000000", "#e53935", "#1e88e5", "#43a047",
                  "#fdd835", "#fb8c00", "#8e24aa", "#ffffff")
PALETTE_RADIUS = 36
PALETTE_GAP = 26
COLOR_BUTTON_SIZE = (110, 42)
STROKE_GAP_SECONDS = 0.2
CONTROL_MARGIN = 16
PALETTE_TOP = 40
COLOR_DWELL_SECONDS = 0.5
CLEAR_DWELL_SECONDS = 0.8
CLEAR_BUTTON_SIZE = (90, 38)

PINCH_ENTER_RATIO = 0.35
PINCH_RELEASE_RATIO = 0.48
# 주먹 속 맞닿은 손끝을 핀치로 오인하지 않도록 최소 펼침 거리 확인
PINCH_INDEX_REACH_RATIO = 0.9
PINCH_THUMB_REACH_RATIO = 1.1
GRAB_HIT_DISTANCE = 24
GRAB_HIGHLIGHT_EXTRA = 8
GRAB_THICKNESS_EXTRA = 2

SPREAD_WINDOW_SECONDS = 0.8
SPREAD_MIN_INCREASE = 0.14  # 손목 거리 증가 / 카메라 프레임 폭
SPREAD_OPEN_FRAMES = 3
SPREAD_CONFIRM_FRAMES = 2
SPREAD_FINGER_RATIO = 1.04
SPREAD_MIN_EXTENDED = 3  # 엄지 제외 네 손가락 중 세 개
SPREAD_MISS_SECONDS = 0.15
SPREAD_MIN_SPEED = 0.25
SPREAD_COOLDOWN_SECONDS = 2.0
TRANSITION_SECONDS = 0.7
TRANSITION_MAX_SCALE = 1.5

SKETCH_SIZE = 1024
SKETCH_MARGIN = 64
CODEX_BINARY = str(Path.home() / ".local/bin/codex")
CODEX_TIMEOUT_SECONDS = 180
ERROR_SECONDS = 3
RESULT_FIST_SECONDS = 2
CODEX_PROMPT = (
    "$imagegen 첨부한 스케치를 바탕으로 그림을 완성해줘. "
    "스케치의 형태와 구도는 유지하고 각 선의 색을 참고해서 자연스럽게 색칠하고 "
    "디테일을 더한 일러스트로 만들어줘. 내장 image_gen 도구를 사용하고 API 키는 사용하지 마. "
    "생성 결과를 {result_path} 에 PNG로 복사해 저장해줘. "
    "스케치 경로는 {sketch_path} 야. 프로젝트 소스는 수정하지 마."
)

HELP_TEXT = (
    "화면 아래 버튼: 전체화면 끄기 / 앱 종료\n"
    "검지 펴기: 그리기 · 주먹: 펜 업\n"
    "검지로 Color 칸: 중앙 팔레트 열기\n"
    "색 / 지우개 위에 0.5초: 선택\n"
    "엄지+검지 핀치: 가까운 획 잡기 / 이동\n"
    "잡은 획을 화면 밖으로 빠르게 던지기: 삭제\n"
    "양손 펼쳐 빠르게 벌리기: AI 생성\n"
    "결과에서 주먹 2초: 새 그림\n"
    "프리뷰 클릭 후 Ctrl+Option +\n"
    "C 지우기 · Z 취소 · G 생성 · D 디버그\n"
    "P 프리뷰 · H 사용법 · V 전체화면 카메라 · Q 종료\n"
    "숨긴 프리뷰는 메뉴 막대 Air Draw에서 다시 열기"
)
ERASER_RADIUS = 18
CAMERA_BACKGROUND_DEFAULT = True
THROW_WINDOW_SECONDS = 0.2
THROW_MIN_SPEED = 1.1
THROW_MIN_DISTANCE = 0.10
THROW_EDGE_MARGIN = 0.045
THROW_RELEASE_SECONDS = 0.18
