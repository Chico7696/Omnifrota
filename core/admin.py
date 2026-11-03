from django.contrib import admin  # Importa o registro administrativo do Django.
from .models import (  # Importa os modelos disponíveis no painel.
	pecas,  # Cadastro de peças.
	veiculos,  # Cadastro de veículos.
	fornecedores,  # Cadastro de fornecedores.
	fabricantes,  # Cadastro de fabricantes.
	pedidos,  # Pedidos de peças.
	funcionarios,  # Funcionários cadastrados.
	estoque,  # Movimentações de estoque.
	ordem_servico,  # Chamados de serviço.
	equipamentos,  # Equipamentos da frota.
	orcamento_ia,  # Orçamentos gerados pela previsão.
)

admin.site.register([  # Habilita a consulta e edição desses modelos no admin.
	pecas,  # Registra peças.
	veiculos,  # Registra veículos.
	fornecedores,  # Registra fornecedores.
	fabricantes,  # Registra fabricantes.
	pedidos,  # Registra pedidos.
	funcionarios,  # Registra funcionários.
	estoque,  # Registra movimentações.
	ordem_servico,  # Registra chamados.
	equipamentos,  # Registra equipamentos.
	orcamento_ia,  # Registra orçamentos.
])
