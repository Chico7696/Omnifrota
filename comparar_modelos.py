
"""
Compara diferentes modelos de regressão para identificar aquele que apresenta
o melhor desempenho na previsão dos valores de orçamentos.

Todos os modelos utilizam o mesmo conjunto de treinamento e teste,
garantindo uma comparação justa entre os algoritmos.

As métricas utilizadas para avaliação são:
- MAE: erro absoluto médio, em reais (R$).
- MAPE: erro percentual absoluto médio.
- R²: coeficiente de determinação.

Uso:
    python comparar_modelos.py
"""

# Importa Path para manipulação de caminhos de arquivos.
from pathlib import Path

# Bibliotecas para manipulação e processamento de dados numéricos.
import numpy as np
import pandas as pd

# ColumnTransformer permite aplicar diferentes tratamentos
# para variáveis categóricas e numéricas.
from sklearn.compose import ColumnTransformer

# Importa os algoritmos de ensemble utilizados na comparação.
from sklearn.ensemble import (
    GradientBoostingRegressor,
    HistGradientBoostingRegressor,
    RandomForestRegressor,
)

# SimpleImputer preenche valores ausentes nos dados.
from sklearn.impute import SimpleImputer

# Ridge é um modelo de regressão linear com regularização L2.
from sklearn.linear_model import Ridge

# Importa as métricas utilizadas para avaliar os modelos.
from sklearn.metrics import (
    mean_absolute_error,
    mean_absolute_percentage_error,
    r2_score,
)

# Divide os dados em conjuntos de treinamento e teste.
from sklearn.model_selection import train_test_split

# Pipeline organiza as etapas de pré-processamento e treinamento.
from sklearn.pipeline import Pipeline

# OneHotEncoder transforma variáveis categóricas em representações numéricas.
from sklearn.preprocessing import OneHotEncoder

# Importa o módulo responsável pela inteligência artificial
# e pelo processamento dos dados de orçamentos.
from orcamentos import ia_preditiva


def construir_preprocessador():
    """
    Constrói o pré-processador responsável por preparar os dados
    antes de serem enviados aos algoritmos de regressão.

    O tratamento é dividido em duas categorias:

    1. Variáveis categóricas:
       - Preenchimento de valores ausentes pela categoria mais frequente.
       - Conversão das categorias em valores numéricos com OneHotEncoder.

    2. Variáveis numéricas:
       - Preenchimento dos valores ausentes pela mediana.
    """

    # Obtém a lista de variáveis categóricas definidas no módulo
    # de inteligência artificial.
    categoricas = list(ia_preditiva.CATEGORICAL_FEATURES)

    # Identifica as variáveis numéricas utilizadas pelo modelo.
    # São consideradas as variáveis originais e as variáveis
    # criadas durante a engenharia de atributos.
    #
    # As variáveis categóricas são excluídas dessa lista para
    # evitar que recebam um tratamento inadequado.
    numericas = [
        coluna
        for coluna in (
            *ia_preditiva.INPUT_FEATURES,
            *ia_preditiva.ENGINEERED_FEATURES
        )
        if coluna not in ia_preditiva.CATEGORICAL_FEATURES
    ]

    # Cria um ColumnTransformer para aplicar tratamentos
    # diferentes conforme o tipo de variável.
    return ColumnTransformer(
        transformers=[

            # Tratamento das variáveis categóricas.
            (
                "categoricas",

                # Pipeline com duas etapas:
                Pipeline(
                    steps=[

                        # Substitui valores ausentes pela categoria
                        # que aparece com maior frequência.
                        ("imputar", SimpleImputer(strategy="most_frequent")),

                        # Transforma categorias em colunas numéricas.
                        # handle_unknown="ignore" evita erros quando
                        # aparecem categorias não vistas no treinamento.
                        ("codificar", OneHotEncoder(handle_unknown="ignore")),
                    ]
                ),

                # Colunas que receberão esse tratamento.
                categoricas,
            ),

            # Tratamento das variáveis numéricas.
            (
                "numericas",

                # Substitui valores ausentes pela mediana
                # de cada variável numérica.
                SimpleImputer(strategy="median"),

                # Colunas que receberão esse tratamento.
                numericas,
            ),
        ]
    )


# Dicionário contendo os modelos de regressão que serão comparados.
#
# Todos os candidatos receberão os mesmos dados de treinamento
# e serão avaliados sobre o mesmo conjunto de teste.
CANDIDATOS = {

    # Modelo Random Forest com 300 árvores.
    # min_samples_leaf=2 exige pelo menos duas amostras
    # em cada folha, ajudando a reduzir o sobreajuste.
    "RandomForest (atual)": RandomForestRegressor(
        n_estimators=300,
        min_samples_leaf=2,
        random_state=42,
        n_jobs=-1
    ),

    # Segunda configuração do Random Forest.
    # Utiliza 500 árvores e permite folhas com apenas uma amostra.
    # Pode capturar padrões mais específicos, mas apresenta
    # maior possibilidade de sobreajuste.
    "RandomForest (leaf=1)": RandomForestRegressor(
        n_estimators=500,
        min_samples_leaf=1,
        random_state=42,
        n_jobs=-1
    ),

    # Gradient Boosting:
    # constrói árvores sequencialmente, em que cada nova árvore
    # busca corrigir os erros cometidos pelas anteriores.
    "GradientBoosting": GradientBoostingRegressor(
        random_state=42
    ),

    # HistGradientBoosting:
    # versão otimizada do Gradient Boosting que utiliza
    # histogramas para acelerar o treinamento.
    "HistGradientBoosting": HistGradientBoostingRegressor(
        random_state=42
    ),

    # Ridge:
    # modelo de regressão linear que utiliza regularização L2
    # para reduzir a complexidade dos coeficientes e ajudar
    # a evitar o sobreajuste.
    "Ridge": Ridge(alpha=1.0),
}


def main() -> None:
    """
    Executa todo o processo de comparação dos modelos:

    1. Carrega os dados dos orçamentos.
    2. Prepara as variáveis de entrada e saída.
    3. Divide os dados em treinamento e teste.
    4. Treina cada modelo.
    5. Calcula as métricas de avaliação.
    6. Identifica o modelo com menor erro absoluto médio.
    """

    # Carrega a base de dados de orçamentos.
    dados = ia_preditiva.carregar_dados()

    # Seleciona as variáveis de entrada e aplica a engenharia
    # de atributos, criando novas variáveis que podem ajudar
    # os modelos a identificar padrões nos dados.
    X = ia_preditiva.criar_variaveis(
        dados.loc[:, ia_preditiva.INPUT_FEATURES]
    )

    # Define a variável que o modelo deverá prever.
    # Neste caso, representa o valor do orçamento.
    y = dados[ia_preditiva.TARGET]

    # Divide os dados em dois conjuntos:
    #
    # 80% para treinamento dos modelos.
    # 20% para avaliação dos modelos.
    #
    # random_state=42 garante que a divisão seja reproduzível.
    # Assim, todos os modelos serão avaliados sobre as mesmas amostras.
    X_treino, X_teste, y_treino, y_teste = train_test_split(
        X,
        y,
        test_size=0.2,
        random_state=42
    )

    # Exibe o cabeçalho da tabela de resultados.
    # Os alinhamentos facilitam a leitura das métricas.
    print(
        f"{'modelo':<24} "
        f"{'MAE (R$)':>12} "
        f"{'MAPE (%)':>10} "
        f"{'R²':>8}"
    )

    # Linha separadora da tabela.
    print("-" * 58)

    # Lista que armazenará o MAE e o nome de cada modelo.
    # Será utilizada posteriormente para identificar
    # o modelo com menor erro absoluto médio.
    resultados = []

    # Percorre todos os modelos definidos no dicionário CANDIDATOS.
    for nome, regressor in CANDIDATOS.items():

        # Cria um Pipeline para integrar o pré-processamento
        # e o algoritmo de regressão.
        #
        # Dessa forma, cada modelo recebe os dados tratados
        # automaticamente antes do treinamento e da previsão.
        modelo = Pipeline(
            steps=[
                ("preprocessar", construir_preprocessador()),
                ("regressor", regressor)
            ]
        )

        # Treina o modelo utilizando os dados de treinamento.
        modelo.fit(X_treino, y_treino)

        # Realiza previsões sobre os dados de teste.
        previsoes = modelo.predict(X_teste)

        # MAE (Mean Absolute Error):
        # calcula a média dos erros absolutos entre os valores
        # reais e os valores previstos.
        #
        # Quanto menor o MAE, mais próximas são as previsões
        # dos valores reais, considerando a escala em reais.
        mae = mean_absolute_error(
            y_teste,
            previsoes
        )

        # MAPE (Mean Absolute Percentage Error):
        # calcula a média dos erros absolutos percentuais.
        #
        # Multiplicamos por 100 para apresentar o resultado
        # em porcentagem.
        #
        # Quanto menor o MAPE, menor o erro percentual médio.
        mape = (
            mean_absolute_percentage_error(
                y_teste,
                previsoes
            ) * 100
        )

        # R² (Coeficiente de Determinação):
        # mede quanto da variação dos valores reais é explicada
        # pelo modelo.
        #
        # Quanto mais próximo de 1, melhor o ajuste.
        # Um resultado negativo indica desempenho inferior
        # ao de prever sempre a média dos valores reais.
        r2 = r2_score(
            y_teste,
            previsoes
        )

        # Armazena o MAE e o nome do modelo para comparação.
        resultados.append((mae, nome))

        # Imprime as métricas calculadas para o modelo atual.
        print(
            f"{nome:<24} "
            f"{mae:>12,.2f} "
            f"{mape:>9.2f}% "
            f"{r2:>8.3f}"
        )

    # Ordena os resultados pelo MAE em ordem crescente.
    # O primeiro elemento será o modelo com menor erro absoluto médio.
    resultados.sort()

    # Exibe o modelo que apresentou o melhor resultado segundo
    # o critério de menor MAE.
    print(
        f"\nMelhor por MAE: {resultados[0][1]} "
        f"(R$ {resultados[0][0]:,.2f})"
    )


# Verifica se o arquivo está sendo executado diretamente.
# Isso evita executar a função main() automaticamente
# quando este módulo for importado por outro arquivo.
if __name__ == "__main__":
    main()
