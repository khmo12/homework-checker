from PIL import Image
import io
import os

MAX_LONG_SIDE = 1800  # 긴 변 기준 리사이즈 크기 (px)
JPEG_QUALITY = 85      # JPEG 압축 품질 (0~100, 85면 화질 저하 거의 안 느껴짐)


def preprocess_image(input_path: str, output_dir: str = "data/_processed") -> str:
    """
    원본 이미지를 받아서:
    - 긴 변이 MAX_LONG_SIDE를 넘으면 비율 유지하며 리사이즈
    - JPEG로 재압축
    - EXIF 방향 정보에 따라 회전 보정 (스마트폰 사진이 눕혀져 보이는 문제 방지)
    - output_dir에 저장하고, 저장된 경로를 반환

    글씨가 뭉개지지 않도록 MAX_LONG_SIDE는 1800px로 설정
    (인수인계 문서 권장 범위 1500~2000px 중간값)
    """
    os.makedirs(output_dir, exist_ok=True)

    img = Image.open(input_path)

    # EXIF 방향 정보 보정 (스마트폰 사진이 옆으로 눕혀져 저장되는 경우 방지)
    img = _fix_orientation(img)

    # RGBA 등 JPEG가 지원 안 하는 모드면 RGB로 변환
    if img.mode != "RGB":
        img = img.convert("RGB")

    width, height = img.size
    long_side = max(width, height)

    if long_side > MAX_LONG_SIDE:
        scale = MAX_LONG_SIDE / long_side
        new_size = (int(width * scale), int(height * scale))
        img = img.resize(new_size, Image.LANCZOS)

    filename = os.path.splitext(os.path.basename(input_path))[0] + "_processed.jpg"
    output_path = os.path.join(output_dir, filename)

    img.save(output_path, "JPEG", quality=JPEG_QUALITY, optimize=True)

    return output_path


def _fix_orientation(img: Image.Image) -> Image.Image:
    """EXIF 회전 정보를 실제 픽셀 회전으로 반영한다."""
    try:
        exif = img.getexif()
        orientation_tag = 274  # EXIF 표준 태그 번호 (Orientation)
        orientation = exif.get(orientation_tag)

        if orientation == 3:
            img = img.rotate(180, expand=True)
        elif orientation == 6:
            img = img.rotate(270, expand=True)
        elif orientation == 8:
            img = img.rotate(90, expand=True)
    except Exception:
        pass  # EXIF 정보가 없거나 읽기 실패해도 그냥 원본 그대로 진행

    return img