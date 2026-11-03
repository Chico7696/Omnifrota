import json
import inspect
import os
import tempfile
import unittest
from pathlib import Path

from django.conf import settings
from django.test.runner import DiscoverRunner
from django.utils import timezone


class ReportTestResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cases = []

    @staticmethod
    def _explicacao(test):
        descricao = test.shortDescription()
        if descricao:
            return descricao

        try:
            metodo = getattr(type(test), test._testMethodName)
            linha = inspect.getsourcelines(metodo)[0][0]
            _, separador, comentario = linha.partition('#')
            if separador and comentario.strip():
                return comentario.strip().rstrip('.')
        except (OSError, TypeError):
            pass

        nome = test._testMethodName.removeprefix('test_').replace('_', ' ')
        return f'Verifica {nome}.'

    def _registrar_caso(self, test, status, detalhe=None, nome=None):
        caso = {
            'nome': nome or self.getDescription(test),
            'explicacao': self._explicacao(test),
            'status': status,
        }
        if detalhe:
            caso['detalhe'] = detalhe
        self.cases.append(caso)

    def addSuccess(self, test):
        super().addSuccess(test)
        self._registrar_caso(test, 'passou')

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self._registrar_caso(test, 'falhou', self._exc_info_to_string(err, test))

    def addError(self, test, err):
        super().addError(test, err)
        self._registrar_caso(test, 'erro', self._exc_info_to_string(err, test))

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self._registrar_caso(test, 'ignorado', reason)

    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test, err)
        self._registrar_caso(test, 'ignorado', 'Falha esperada pelo teste.')

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test)
        self._registrar_caso(
            test,
            'falhou',
            'O teste passou apesar de estar marcado como falha esperada.',
        )

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err is None:
            return
        status = 'falhou' if issubclass(err[0], test.failureException) else 'erro'
        self._registrar_caso(
            test,
            status,
            self._exc_info_to_string(err, test),
            nome=f'{self.getDescription(test)} ({subtest})',
        )


class TestReportRunner(DiscoverRunner):
    def get_resultclass(self):
        return ReportTestResult

    def run_suite(self, suite, **kwargs):
        resultado = super().run_suite(suite, **kwargs)
        if hasattr(resultado, 'cases'):
            self._salvar_relatorio(resultado)
        return resultado

    @staticmethod
    def _salvar_relatorio(resultado):
        totais = {
            'passou': sum(caso['status'] == 'passou' for caso in resultado.cases),
            'falhou': sum(caso['status'] == 'falhou' for caso in resultado.cases),
            'erro': sum(caso['status'] == 'erro' for caso in resultado.cases),
            'ignorado': sum(caso['status'] == 'ignorado' for caso in resultado.cases),
        }
        documento = {
            'executado_em': timezone.localtime().isoformat(timespec='seconds'),
            'total': resultado.testsRun,
            'totais': totais,
            'status': 'aprovado' if resultado.wasSuccessful() else 'com_falhas',
            'casos': resultado.cases,
        }
        diretorio = Path(settings.BASE_DIR) / '.test-results'
        diretorio.mkdir(parents=True, exist_ok=True)
        descritor, caminho_temporario = tempfile.mkstemp(dir=diretorio, suffix='.tmp')
        try:
            with os.fdopen(descritor, 'w', encoding='utf-8') as arquivo:
                json.dump(documento, arquivo, ensure_ascii=False, indent=2)
            os.replace(caminho_temporario, diretorio / 'latest.json')
        finally:
            if os.path.exists(caminho_temporario):
                os.unlink(caminho_temporario)