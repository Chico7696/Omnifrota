"""Simulações da IA preditiva de orçamento integrada ao Django.

Executa:
  1. Cenários variados passando pelo formulário (OrcamentoIAForm);
  2. O mapeamento para as variáveis do modelo (_campo_predicao) e a previsão;
  3. Testes de borda do módulo orcamentos.ia_preditiva (erros esperados).

Uso:
    python simular_orcamentos.py
"""

import os
from pathlib import Path

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "omnifrota.settings")
django.setup()

from orcamentos import ia_preditiva  # noqa: E402
from core.forms import OrcamentoIAForm  # noqa: E402
from core.views import _campo_predicao, _prever_orcamento  # noqa: E402


CENARIOS = [
    {
        "rotulo": "Van leve, sem manutenção recente",
        "dados": {
            "veiculo": "Van", "modelo": "Sprinter", "ano_veiculo": 2021,
            "tempo_uso": 24, "quilometragem": 110000, "peso_toneladas": "8.0",
            "qtd_veiculos": 1, "qtd_pecas": 2, "valor_pecas": "450.00",
            "tipo_veiculo": "1", "funcionalidade": "1",
            "manutencao_recente": "0", "data_ultima_manutencao": "",
            "valor_ultima_manutencao": "0.00",
        },
    },
    {
        "rotulo": "Caminhão pesado, manutenção recente",
        "dados": {
            "veiculo": "Caminhão", "modelo": "Actros", "ano_veiculo": 2016,
            "tempo_uso": 96, "quilometragem": 550000, "peso_toneladas": "22.0",
            "qtd_veiculos": 3, "qtd_pecas": 12, "valor_pecas": "4800.00",
            "tipo_veiculo": "3", "funcionalidade": "3",
            "manutencao_recente": "1", "data_ultima_manutencao": "2024-05-01",
            "valor_ultima_manutencao": "650000.00",
        },
    },
    {
        "rotulo": "Carro médio, uso moderado",
        "dados": {
            "veiculo": "Carro", "modelo": "Corolla", "ano_veiculo": 2019,
            "tempo_uso": 48, "quilometragem": 210000, "peso_toneladas": "12.0",
            "qtd_veiculos": 1, "qtd_pecas": 3, "valor_pecas": "900.00",
            "tipo_veiculo": "1", "funcionalidade": "2",
            "manutencao_recente": "1", "data_ultima_manutencao": "2023-11-10",
            "valor_ultima_manutencao": "1800.00",
        },
    },
    {
        "rotulo": "Frota grande, frete pesado",
        "dados": {
            "veiculo": "Carreta", "modelo": "R450", "ano_veiculo": 2014,
            "tempo_uso": 120, "quilometragem": 800000, "peso_toneladas": "40.0",
            "qtd_veiculos": 5, "qtd_pecas": 20, "valor_pecas": "9000.00",
            "tipo_veiculo": "3", "funcionalidade": "3",
            "manutencao_recente": "1", "data_ultima_manutencao": "2025-01-05",
            "valor_ultima_manutencao": "12000.00",
        },
    },
]


def separador(titulo: str) -> None:
    print("\n" + "=" * 70)
    print(titulo)
    print("=" * 70)


def rodar_cenarios() -> None:
    separador("1) CENÁRIOS DE ORÇAMENTO")
    for cenario in CENARIOS:
        print(f"\n>> {cenario['rotulo']}")
        form = OrcamentoIAForm(data=cenario["dados"])
        if not form.is_valid():
            print(f"   [FALHA] formulário inválido: {form.errors.as_json()}")
            continue

        caso = _campo_predicao(form.cleaned_data)
        print(f"   entrada do modelo: {caso}")

        previsao, total, desvio = _prever_orcamento(caso)
        print(f"   previsão mensal : {[f'R$ {v:,.2f}' for v in previsao]}")
        print(f"   valor total     : R$ {total:,.2f}")
        print(f"   taxa de desvio  : {desvio}")


def rodar_bordas() -> None:
    separador("2) TESTES DE BORDA DO MÓDULO ia_preditiva")

    print("\n>> prever() sem todos os campos obrigatórios")
    try:
        ia_preditiva.prever({"qtd_veiculos": 1})
    except ValueError as erro:
        print(f"   ValueError esperado: {erro}")

    print("\n>> prever() com modelo inexistente")
    try:
        ia_preditiva.prever(
            {coluna: 0 for coluna in ia_preditiva.INPUT_FEATURES},
            caminho_modelo=Path("modelo_inexistente.joblib"),
        )
    except FileNotFoundError as erro:
        print(f"   FileNotFoundError esperado: {erro}")

    print("\n>> carregar_dados() com CSV de cabeçalho aceito")
    dados = ia_preditiva.carregar_dados()
    print(f"   linhas carregadas: {len(dados)}")
    print(f"   colunas: {list(dados.columns)}")


def rodar_reprodutibilidade() -> None:
    separador("3) REPRODUTIBILIDADE DO MODELO")
    caso = {
        "qtd_veiculos": 3, "qtd_pecas": 12, "ano_fabricacao": 2016,
        "peso_toneladas": 22.0, "tipo_veiculo": 3, "funcionalidade": 3,
        "quilometragem": 550000, "tempo_uso_meses": 96,
        "manutencao_recente": 1, "data_ultima_manutencao": 1,
        "valor_ultima_manutencao": 650000.0, "valor_pecas": 4800.0,
    }
    p1 = ia_preditiva.prever(caso)
    p2 = ia_preditiva.prever(caso)
    print(f"   previsão 1: R$ {p1:,.2f}")
    print(f"   previsão 2: R$ {p2:,.2f}")
    print(f"   determinística: {p1 == p2}")


if __name__ == "__main__":
    if not ia_preditiva.MODEL_PATH.exists():
        print("Modelo ausente; treinando...")
        ia_preditiva.treinar()
    rodar_cenarios()
    rodar_bordas()
    rodar_reprodutibilidade()
    separador("FIM DAS SIMULAÇÕES")
