import os


class PathUtil:
    @staticmethod
    def exists(path):
        return os.path.exists(path)
