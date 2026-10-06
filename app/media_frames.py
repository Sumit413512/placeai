"""Bounded isolated decoder for three thumbnail observations, not full video."""
import base64
import io
import json
import sys


def main():
    # Render/Linux enforces native-decoder limits; other hosts retain the parent
    # wall-clock timeout, input, dimensions, decoded-frame and output bounds.
    if sys.platform != "win32":
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
    import av
    targets = json.loads(sys.argv[1])
    if not isinstance(targets, list) or not 1 <= len(targets) <= 3 or any(not 0 <= n <= 600 for n in targets):
        raise ValueError("Invalid observation window")
    data = sys.stdin.buffer.read(25 * 1024 * 1024 + 1)
    if len(data) > 25 * 1024 * 1024:
        raise ValueError("Media limit")
    images = []
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
            if len(images) < len(targets) and frame.time >= targets[len(images)]:
                image = frame.reformat(width=256, height=max(1, round(frame.height * 256 / frame.width))).to_image()
                output = io.BytesIO()
                image.save(output, format="JPEG", quality=60)
                images.append({"at_seconds": round(frame.time, 3),
                               "image": "data:image/jpeg;base64," + base64.b64encode(output.getvalue()).decode("ascii")})
                if len(images) == len(targets):
                    break
    if not images:
        raise ValueError("No video evidence")
    sys.stdout.write(json.dumps(images))


if __name__ == "__main__":
    main()
