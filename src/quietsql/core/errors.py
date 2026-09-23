class QuietsqlError(Exception):
    pass


class SqlRejected(QuietsqlError):
    pass


class QueryFailed(QuietsqlError):
    pass


class QueryTimeout(QueryFailed):
    pass


class SourceRejected(QuietsqlError):
    pass


class ModelsMissing(QuietsqlError):
    pass


class ConfigRejected(QuietsqlError):
    pass


class DownloadFailed(QuietsqlError):
    pass


class Cancelled(QuietsqlError):
    pass
