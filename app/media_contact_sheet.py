"""Decode one bounded contact sheet from up to four HR-answer midpoints.

This process is intentionally isolated from the API/worker process because native media
decoders handle untrusted student recordings. The output is a small JPEG contact sheet plus
the actual decoded timestamps; it never persists media or emits raw video frames.
"""
import base64
import io
import json
import math
import sys


MAX_MEDIA_BYTES = 25 * 1024 * 1024
PANEL_WIDTH = 256
PANEL_HEIGHT = 144
LABEL_HEIGHT = 22


def main():
    # Render/Linux enforces native-decoder limits; other hosts retain the parent
    # wall-clock timeout, input, dimensions, decoded-frame and output bounds.
    if sys.platform != "win32":
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_CPU, (15, 15))

    import av
    from PIL import Image, ImageDraw

    targets = json.loads(sys.argv[1])
    if (
        not isinstance(targets, list)
        or not 1 <= len(targets) <= 4
        or any(not isinstance(value, (int, float)) or not 0 <= value <= 600 for value in targets)
        or targets != sorted(targets)
    ):
        raise ValueError("Invalid observation targets")

    data = sys.stdin.buffer.read(MAX_MEDIA_BYTES + 1)
    if len(data) > MAX_MEDIA_BYTES:
        raise ValueError("Media limit")

    decoded = []
    with av.open(io.BytesIO(data), mode="r", options={"threads": "1"}) as container:
        streams = list(container.streams.video)
        if not streams:
            raise ValueError("No video evidence")
        stream = streams[0]
        stream.thread_count = 1
        if not 0 < stream.codec_context.width <= 1920 or not 0 < stream.codec_context.height <= 1080:
            raise ValueError("Video dimensions exceed limit")

        for count, frame in enumerate(container.decode(stream)):
            if count >= 18000 or frame.time is None:
                raise ValueError("Decode limit")
            if len(decoded) < len(targets) and frame.time >= targets[len(decoded)]:
                image = frame.to_image().convert("RGB").resize((PANEL_WIDTH, PANEL_HEIGHT))
                decoded.append((round(float(frame.time), 3), image))
                if len(decoded) == len(targets):
                    break

    if not decoded:
        raise ValueError("No video evidence")

    columns = 1 if len(decoded) == 1 else 2
    rows = math.ceil(len(decoded) / columns)
    cell_height = LABEL_HEIGHT + PANEL_HEIGHT
    sheet = Image.new("RGB", (columns * PANEL_WIDTH, rows * cell_height), "white")
    draw = ImageDraw.Draw(sheet)
    panels = []
    for index, (timestamp, image) in enumerate(decoded):
        column = index % columns
        row = index // columns
        left = column * PANEL_WIDTH
        top = row * cell_height
        draw.text((left + 6, top + 4), f"Panel {index + 1}", fill="black")
        sheet.paste(image, (left, top + LABEL_HEIGHT))
        panels.append({"panel": index + 1, "at_seconds": timestamp})

    output = io.BytesIO()
    sheet.save(output, format="JPEG", quality=60, optimize=True)
    encoded = base64.b64encode(output.getvalue()).decode("ascii")
    sys.stdout.write(json.dumps({
        "panels": panels,
        "image": "data:image/jpeg;base64," + encoded,
    }))


if __name__ == "__main__":
    main()
