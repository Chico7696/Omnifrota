"""Treina e usa um modelo local para estimar o valor de orçamentos."""

from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, PolynomialFeatures, StandardScaler

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_PATH = PROJECT_DIR / "dados_orcamentos.csv"
MODEL_PATH = PROJECT_DIR / "modelo_orcamento.joblib"

TARGET = "valor_orcamento"
CATEGORICAL_FEATURES = ("tipo_veiculo", "funcionalidade")
INPUT_FEATURES = (
    "qtd_veiculos",
    "qtd_pecas",
    "ano_fabricacao",
    "peso_toneladas",
    "tipo_veiculo",
    "funcionalidade",
    "quilometragem",
    "tempo_uso_meses",
    "manutencao_recente",
    "data_ultima_manutencao",
    "valor_ultima_manutencao",
    "valor_pecas",
)
CSV_COLUMNS = (TARGET, *INPUT_FEATURES)
ENGINEERED_FEATURES = (
    "pecas_por_veiculo",
    "quilometragem_por_mes_de_uso",
    "valor_medio_por_peca",
    "manutencao_por_veiculo",
)
MIN_ROWS_FOR_EVALUATION = 10
# Taxa de desvio usada quando não há dados suficientes para medi-la.
TAXA_DESVIO_PADRAO = 0.10
# Limites para manter a taxa de desvio dentro de uma faixa razoável.
TAXA_DESVIO_MINIMA = 0.02
TAXA_DESVIO_MAXIMA = 0.15


def carregar_dados(caminho: Path = DATA_PATH) -> pd.DataFrame:
    """Lê CSV com ou sem cabeçalho e informa valores inválidos com a linha."""
    dados = pd.read_csv(caminho, header=None, names=CSV_COLUMNS, skipinitialspace=True)

    if not dados.empty and tuple(
        str(valor).strip() for valor in dados.iloc[0]
    ) == CSV_COLUMNS:
        dados = dados.iloc[1:].copy()

    colunas_numericas = (TARGET, *(col for col in INPUT_FEATURES if col not in CATEGORICAL_FEATURES))
    for coluna in colunas_numericas:
        original = dados[coluna]
        convertido = pd.to_numeric(original, errors="coerce")
        invalidos = original.notna() & convertido.isna()
        if invalidos.any():
            indice = invalidos[invalidos].index[0]
            valor = original.loc[indice]
            raise ValueError(
                f"Valor inválido na linha {indice + 1}, coluna '{coluna}': {valor!r}."
            )
        if coluna == TARGET and convertido.isna().any():
            indice = convertido[convertido.isna()].index[0]
            raise ValueError(
                f"Valor do orçamento ausente na linha {indice + 1} do arquivo {caminho}."
            )
        dados[coluna] = convertido

    dados = dados.drop_duplicates().reset_index(drop=True)
    if dados.empty:
        raise ValueError(f"Nenhum orçamento válido foi encontrado em {caminho}.")
    return dados


def criar_variaveis(dados: pd.DataFrame) -> pd.DataFrame:
    """Acrescenta medidas derivadas sem exigir novos campos no formulário."""
    resultado = dados.copy()
    quantidade_veiculos = resultado["qtd_veiculos"].where(resultado["qtd_veiculos"] > 0)
    quantidade_pecas = resultado["qtd_pecas"].where(resultado["qtd_pecas"] > 0)
    meses_de_uso = resultado["tempo_uso_meses"].where(resultado["tempo_uso_meses"] > 0)

    resultado["pecas_por_veiculo"] = resultado["qtd_pecas"] / quantidade_veiculos
    resultado["quilometragem_por_mes_de_uso"] = resultado["quilometragem"] / meses_de_uso
    resultado["valor_medio_por_peca"] = resultado["valor_pecas"] / quantidade_pecas
    resultado["manutencao_por_veiculo"] = (
        resultado["valor_ultima_manutencao"] / quantidade_veiculos
    )
    return resultado


def criar_modelo() -> Pipeline:
    categoricas = list(CATEGORICAL_FEATURES)
    numericas = [
        coluna
        for coluna in (*INPUT_FEATURES, *ENGINEERED_FEATURES)
        if coluna not in CATEGORICAL_FEATURES
    ]
    preprocessador = ColumnTransformer(
        transformers=[
            (
                "categoricas",
                Pipeline(
                    steps=[
                        ("imputar", SimpleImputer(strategy="most_frequent")),
                        ("codificar", OneHotEncoder(handle_unknown="ignore")),
                    ]
                ),
                categoricas,
            ),
            (
                "numericas",
                Pipeline(
                    steps=[
                        ("imputar", SimpleImputer(strategy="median")),
                        ("padronizar", StandardScaler()),
                        # Termos quadráticos e interações: capturam relações
                        # não lineares (ex.: peso x peças) e reduzem o erro.
                        ("expansao", PolynomialFeatures(degree=2, include_bias=False)),
                    ]
                ),
                numericas,
            ),
        ]
    )
    return Pipeline(
        steps=[
            ("preprocessar", preprocessador),
            ("regressor", Ridge(alpha=1.0)),
        ]
    )


def treinar(
    caminho_dados: Path = DATA_PATH,
    caminho_modelo: Path = MODEL_PATH,
) -> Pipeline:
    dados = carregar_dados(caminho_dados)
    X = criar_variaveis(dados.loc[:, INPUT_FEATURES])
    y = dados[TARGET]
    modelo = criar_modelo()
    taxa_desvio = TAXA_DESVIO_PADRAO

    if len(dados) >= MIN_ROWS_FOR_EVALUATION:
        X_treino, X_teste, y_treino, y_teste = train_test_split(
            X, y, test_size=0.2, random_state=42
        )
        modelo.fit(X_treino, y_treino)
        previsoes = modelo.predict(X_teste)
        mae = mean_absolute_error(y_teste, previsoes)
        print(f"Erro médio absoluto (MAE): R$ {mae:,.2f}")
        if len(y_teste) >= 2:
            print(f"R²: {r2_score(y_teste, previsoes):.3f}")
        taxa_desvio = calcular_taxa_desvio(mae, y_teste)
        print(f"Taxa de desvio estimada: {taxa_desvio:.2%}")
    else:
        print(
            f"Aviso: há apenas {len(dados)} orçamentos únicos. "
            f"São necessários pelo menos {MIN_ROWS_FOR_EVALUATION} para avaliar "
            "o modelo com uma divisão treino/teste; as métricas foram omitidas."
        )

    modelo.fit(X, y)
    caminho_modelo.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"modelo": modelo, "taxa_desvio": taxa_desvio}, caminho_modelo)
    exibir_importancias(modelo)
    print(f"Modelo salvo em: {caminho_modelo}")
    return modelo


def calcular_taxa_desvio(mae: float, valores_reais: pd.Series) -> float:
    """Converte o MAE num desvio percentual sobre o valor médio previsto.

    Representa a margem de erro esperada do modelo, limitada a uma faixa
    razoável para não gerar taxas irreais em datasets muito pequenos.
    """
    media = float(pd.Series(valores_reais).mean())
    if media <= 0:
        return TAXA_DESVIO_PADRAO
    taxa = mae / media
    return float(np.clip(taxa, TAXA_DESVIO_MINIMA, TAXA_DESVIO_MAXIMA))


def carregar_taxa_desvio(caminho_modelo: Path = MODEL_PATH) -> float:
    """Lê a taxa de desvio salva junto ao modelo treinado."""
    if not caminho_modelo.exists():
        return TAXA_DESVIO_PADRAO
    artefato = joblib.load(caminho_modelo)
    return float(artefato.get("taxa_desvio", TAXA_DESVIO_PADRAO))


def exibir_importancias(modelo: Pipeline, limite: int = 10) -> None:
    regressor = modelo.named_steps["regressor"]
    nomes = modelo.named_steps["preprocessar"].get_feature_names_out()

    if hasattr(regressor, "feature_importances_"):
        valores = regressor.feature_importances_
        titulo = "Variáveis mais importantes"
    elif hasattr(regressor, "coef_"):
        # Modelos lineares: usamos o módulo do coeficiente padronizado.
        valores = np.abs(np.ravel(regressor.coef_))
        titulo = "Variáveis de maior peso"
    else:
        return

    importancias = pd.Series(valores, index=nomes).sort_values(ascending=False)
    print(f"\n{titulo} (até {limite}):")
    print(importancias.head(limite).to_string())


def prever(
    caso: dict[str, Any],
    caminho_modelo: Path = MODEL_PATH,
) -> float:
    faltantes = sorted(set(INPUT_FEATURES) - caso.keys())
    if faltantes:
        raise ValueError(f"Campos obrigatórios ausentes para a previsão: {', '.join(faltantes)}.")
    if not caminho_modelo.exists():
        raise FileNotFoundError(
            f"Modelo não encontrado em {caminho_modelo}. Execute o treinamento primeiro."
        )

    artefato = joblib.load(caminho_modelo)
    entrada = criar_variaveis(pd.DataFrame([{chave: caso[chave] for chave in INPUT_FEATURES}]))
    return float(artefato["modelo"].predict(entrada)[0])


if __name__ == "__main__":
    treinar()
