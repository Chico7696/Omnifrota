from django.urls import path, include  # Define e compõe rotas Django.
from . import views  # Importa as funções que atendem às rotas do aplicativo.

urlpatterns = [  # Declara os caminhos públicos e protegidos do app.
    path('accounts/', include('django.contrib.auth.urls')),  # Inclui as rotas padrão de autenticação.
    path('neymar/', views.pagina_neymar, name='pagina_neymar'),  # Exibe a página especial.
    path('home/', views.home, name='home'),  # Direciona o usuário conforme seu cargo.
    path('', views.login_usuario, name='login'),  # Usa o login como página inicial.
    path('logout/', views.logout_usuario, name='logout'),  # Encerra a sessão autenticada.
    path('registrar/', views.registrar_usuario, name='registrar'),  # Cria uma conta de usuário.
    path('gerenciar-cargos/', views.gerenciar_cargos, name='gerenciar_cargos'),  # Administra os cargos dos usuários.
    path('resultados-testes/', views.resultados_testes, name='resultados_testes'),  # Exibe o último relatório de testes.

    path('adicionar_peca/', views.adicionar_peca, name='adicionar_peca'),  # Cadastra peças.
    path('lista_pecas/', views.lista_pecas, name='lista_pecas'),  # Lista e filtra peças.
    path('editar_peca/<int:id>/', views.editar_peca, name='editar_peca'),  # Atualiza uma peça pelo identificador.
    path('excluir_peca/<int:id>/', views.excluir_peca, name='excluir_peca'),  # Remove uma peça pelo identificador.

    path('equipamentos/', views.equipamentos_view, name='equipamentos'),  # Lista equipamentos e seus estados.
    path('equipamentos/<int:id>/status/', views.alterar_status_equipamento, name='alterar_status_equipamento'),  # Atualiza status de equipamento.
    path('fornecedores/', views.fornecedores_view, name='fornecedores'),  # Lista fornecedores.
    path('pedidos/', views.pedidos_view, name='pedidos'),  # Cria e consulta pedidos.
    path('pedidos/<int:id_pedido>/entregue/', views.marcar_pedido_entregue, name='marcar_pedido_entregue'),  # Marca pedido enviado como entregue.
    path('chamados/', views.chamados, name='chamados'),  # Abre chamados de serviço.
    path('relatorios/', views.relatorios, name='relatorios'),  # Exibe movimentações e chamados.
    path('chamados/<int:id>/status/', views.alterar_status_chamado, name='alterar_status_chamado'),  # Atualiza estado do chamado.
    path('estoque/entrada/', views.registrar_entrada_estoque, name='registrar_entrada_estoque'),  # Registra entradas de estoque.
    path('estoque/<int:id>/saida/', views.registrar_saida_estoque, name='registrar_saida_estoque'),  # Registra baixas de estoque.

    path('orcamento_form/', views.orcamento_form_view, name='orcamento_form'),  # Gera um novo orçamento.
    path('orcamento_grafico/', views.orcamento_grafico_view, name='orcamento_grafico'),  # Exibe o orçamento mais recente.
    path('orcamento_grafico/<int:id_orcamento>/', views.orcamento_grafico_view, name='orcamento_grafico'),  # Exibe um orçamento escolhido.
    path('orcamentos_historico/', views.orcamentos_historico_view, name='orcamentos_historico'),  # Consulta o histórico de previsões.
    path('orcamento_pdf/<int:id_orcamento>/', views.orcamento_pdf_view, name='orcamento_pdf'),  # Baixa um orçamento em PDF.
]
