"""Demonstra a IA preditiva integrada com um dataset maior.

Este script:
  1. Gera um dataset sintético com a mesma estrutura de colunas;
  2. Treina o modelo com MAE/R² (agora com dados para avaliação);
  3. Roda os mesmos cenários e mostra que as previsões passam a diferenciar.

Não altera o modelo de produção; treina num arquivo temporário.

Uso:
    python simular_dataset_maior.py
"""

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from orcamentos import ia_preditiva

RNG = np.random.default_rng(42)
N_LINHAS = 300

TIPOS = [1, 2, 3]
FUNCIONALIDADES = [1, 2, 3]


def gerar_dataset(n: int = N_LINHAS) -> pd.DataFrame:
    """Simula orçamentos com relação plausível entre as variáveis e o alvo."""
    qtd_veiculos = RNG.integers(1, 6, n)
    qtd_pecas = RNG.integers(0, 25, n)
    ano_fabricacao = RNG.integers(2010, 2024, n)
    peso_toneladas = RNG.uniform(1.2, 40.0, n).round(2)
    tipo_veiculo = RNG.choice(TIPOS, n)
    funcionalidade = RNG.choice(FUNCIONALIDADES, n)
    quilometragem = RNG.integers(10_000, 900_000, n)
    tempo_uso_meses = RNG.integers(1, 180, n)
    manutencao_recente = RNG.integers(0, 2, n)
    data_ultima_manutencao = RNG.integers(0, 2, n)
    valor_ultima_manutencao = (RNG.uniform(0, 15_000, n)).round(2)
    valor_pecas = (RNG.uniform(0, 10_000, n)).round(2)

    # Regra geradora: peças, peso, quilometragem e manutenção elevam o custo.
    ruido = RNG.normal(0, 300, n)
    valor = (
        500.0 * qtd_veiculos
        + 180.0 * qtd_pecas
        + 250.0 * peso_toneladas
        + 0.004 * quilometragem
        + 12.0 * tempo_uso_meses
        + 0.15 * valor_ultima_manutencao
        + 0.30 * valor_pecas
        + 400.0 * manutencao_recente
        + 800.0 * tipo_veiculo
        + ruido
    ).round(2)

    return pd.DataFrame(
        {
            "valor_orcamento": valor,
            "qtd_veiculos": qtd_veiculos,
            "qtd_pecas": qtd_pecas,
            "ano_fabricacao": ano_fabricacao,
            "peso_toneladas": peso_toneladas,
            "tipo_veiculo": tipo_veiculo,
            "funcionalidade": funcionalidade,
            "quilometragem": quilometragem,
            "tempo_uso_meses": tempo_uso_meses,
            "manutencao_recente": manutencao_recente,
            "data_ultima_manutencao": data_ultima_manutencao,
            "valor_ultima_manutencao": valor_ultima_manutencao,
            "valor_pecas": valor_pecas,
        }
    )


CENARIOS = [
    ("Van leve, sem manutenção", dict(
        qtd_veiculos=1, qtd_pecas=2, ano_fabricacao=2021, peso_toneladas=8.0,
        tipo_veiculo=1, funcionalidade=1, quilometragem=110000, tempo_uso_meses=24,
        manutencao_recente=0, data_ultima_manutencao=0,
        valor_ultima_manutencao=0.0, valor_pecas=450.0)),
    ("Caminhão pesado, manutenção", dict(
        qtd_veiculos=3, qtd_pecas=12, ano_fabricacao=2016, peso_toneladas=22.0,
        tipo_veiculo=3, funcionalidade=3, quilometragem=550000, tempo_uso_meses=96,
        manutencao_recente=1, data_ultima_manutencao=1,
        valor_ultima_manutencao=650000.0, valor_pecas=4800.0)),
    ("Carro médio", dict(
        qtd_veiculos=1, qtd_pecas=3, ano_fabricacao=2019, peso_toneladas=12.0,
        tipo_veiculo=1, funcionalidade=2, quilometragem=210000, tempo_uso_meses=48,
        manutencao_recente=1, data_ultima_manutencao=1,
        valor_ultima_manutencao=1800.0, valor_pecas=900.0)),
    ("Frota grande, frete pesado", dict(
        qtd_veiculos=5, qtd_pecas=20, ano_fabricacao=2014, peso_toneladas=40.0,
        tipo_veiculo=3, funcionalidade=3, quilometragem=800000, tempo_uso_meses=120,
        manutencao_recente=1, data_ultima_manutencao=1,
        valor_ultima_manutencao=12000.0, valor_pecas=9000.0)),
]


def main() -> None:
    dados = gerar_dataset()
    with tempfile.TemporaryDirectory() as tmp:
        caminho_dados = Path(tmp) / "orcamentos.csv"
        caminho_modelo = Path(tmp) / "modelo_teste.joblib"
        dados.to_csv(caminho_dados, index=False, header=False)

        print("=" * 70)
        print(f"TREINO COM DATASET SINTÉTICO ({len(dados)} linhas)")
        print("=" * 70)
        ia_preditiva.treinar(caminho_dados, caminho_modelo)

        print("\n" + "=" * 70)
        print("PREVISÕES POR CENÁRIO (dataset maior)")
        print("=" * 70)
        for rotulo, caso in CENARIOS:
            valor = ia_preditiva.prever(caso, caminho_modelo=caminho_modelo)
            print(f"   {rotulo:<32} -> R$ {valor:>12,.2f}")

        valores = [ia_preditiva.prever(c, caminho_modelo=caminho_modelo) for _, c in CENARIOS]
        print(f"\n   cenários distintos: {len(set(round(v, 2) for v in valores))} de {len(valores)}")


if __name__ == "__main__":
    main()
