def load_config(path):
    with open(path, encoding="utf-8") as stream:
        return stream.read()


def validate_config(data):
    return bool(data.strip())
