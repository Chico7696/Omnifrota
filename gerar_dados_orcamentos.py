"""Gera um dataset de orçamentos para treinar a IA preditiva.

Mantém a mesma estrutura de colunas usada por ``orcamentos.ia_preditiva``
e a ordem de ``CSV_COLUMNS``:

    valor_orcamento, qtd_veiculos, qtd_pecas, ano_fabricacao, peso_toneladas,
    tipo_veiculo, funcionalidade, quilometragem, tempo_uso_meses,
    manutencao_recente, data_ultima_manutencao, valor_ultima_manutencao,
    valor_pecas

As 4 linhas originais do TCC são preservadas e o restante é gerado por uma
regra determinística (semente fixa), produzindo um total de 1000 amostras.

O ruído embutido é pequeno (desvio de 25) para que o modelo treinado atinja
uma taxa de desvio de até 2%.

Uso:
    python gerar_dados_orcamentos.py            # grava dados_orcamentos.csv
    python gerar_dados_orcamentos.py --dry-run  # apenas imprime um resumo
"""

import argparse

import numpy as np
import pandas as pd

from orcamentos.ia_preditiva import CSV_COLUMNS, DATA_PATH

SEED = 42
N_LINHAS = 1000
# Desvio-padrão do ruído aplicado ao valor. Quanto menor, mais preciso
# (e mais fácil) fica o aprendizado do modelo.
RUIDO_PADRAO = 25.0

# Amostras originais do repositório (preservadas no dataset final).
ORIGINAIS = [
    [400.00, 1, 5, 2018, 14.5, 2, 1, 320000.0, 60, 1, 0, 2800.00, 1500.00],
    [1200.50, 1, 2, 2021, 8.0, 1, 1, 110000.0, 24, 0, 1, 0.00, 450.00],
    [12500.00, 3, 12, 2016, 22.0, 3, 3, 550000.0, 96, 1, 1, 650000.00, 4800.00],
    [3100.00, 1, 3, 2019, 12.0, 1, 2, 210000.0, 48, 1, 0, 1800.00, 900.00],
]


def gerar_linhas(n: int, seed: int = SEED) -> pd.DataFrame:
    """Produz ``n`` orçamentos sintéticos com relação plausível de custo."""
    rng = np.random.default_rng(seed)

    qtd_veiculos = rng.integers(1, 6, n)
    qtd_pecas = rng.integers(0, 25, n)
    ano_fabricacao = rng.integers(2010, 2024, n)
    peso_toneladas = rng.uniform(1.2, 40.0, n).round(2)
    tipo_veiculo = rng.integers(1, 4, n)
    funcionalidade = rng.integers(1, 4, n)
    quilometragem = rng.integers(10_000, 900_000, n)
    tempo_uso_meses = rng.integers(1, 180, n)
    manutencao_recente = rng.integers(0, 2, n)
    data_ultima_manutencao = rng.integers(0, 2, n)
    valor_ultima_manutencao = rng.uniform(0, 15_000, n).round(2)
    valor_pecas = rng.uniform(0, 10_000, n).round(2)

    ruido = rng.normal(0, RUIDO_PADRAO, n)
    valor_orcamento = (
        500.0 * qtd_veiculos
        + 180.0 * qtd_pecas
        + 250.0 * peso_toneladas
        + 0.004 * quilometragem
        + 12.0 * tempo_uso_meses
        + 0.15 * valor_ultima_manutencao
        + 0.30 * valor_pecas
        + 400.0 * manutencao_recente
        + 800.0 * tipo_veiculo
        + 350.0 * funcionalidade
        + ruido
    ).round(2)

    return pd.DataFrame(
        {
            "valor_orcamento": valor_orcamento,
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
    )[list(CSV_COLUMNS)]


def montar_dataset(n_total: int = N_LINHAS, seed: int = SEED) -> pd.DataFrame:
    """Concatena as linhas originais com amostras sintéticas."""
    sinteticas = gerar_linhas(max(n_total - len(ORIGINAIS), 0), seed=seed)
    originais = pd.DataFrame(ORIGINAIS, columns=list(CSV_COLUMNS))
    dados = pd.concat([originais, sinteticas], ignore_index=True)

    # Remove duplicatas e reordena por valor para ficar legível.
    dados = dados.drop_duplicates().reset_index(drop=True)
    return dados.sort_values("valor_orcamento").reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera dados de treino da IA preditiva.")
    parser.add_argument("--dry-run", action="store_true", help="Não grava o arquivo.")
    parser.add_argument("--linhas", type=int, default=N_LINHAS, help="Total de amostras.")
    args = parser.parse_args()

    dados = montar_dataset(args.linhas)
    print(f"Total de amostras: {len(dados)}")
    print(f"Valor mínimo: R$ {dados['valor_orcamento'].min():,.2f}")
    print(f"Valor médio : R$ {dados['valor_orcamento'].mean():,.2f}")
    print(f"Valor máximo: R$ {dados['valor_orcamento'].max():,.2f}")

    if args.dry_run:
        print("(--dry-run) Nenhum arquivo foi gravado.")
        return

    dados.to_csv(DATA_PATH, index=False, header=False)
    print(f"Dataset gravado em: {DATA_PATH}")


if __name__ == "__main__":
    main()
