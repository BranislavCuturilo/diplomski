"""Tehnicka strana Django-a bez promenljivih okvira: inace ispisuje seme i istoriju partije."""

from django.views.debug import SafeExceptionReporterFilter


class FilterBezPromenljivih(SafeExceptionReporterFilter):
    def get_traceback_frame_variables(self, request, tb_frame):
        return []
