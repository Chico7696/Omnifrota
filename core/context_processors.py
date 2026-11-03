from .access_control import (  # Reutiliza a verificação de cargos nas páginas.
    ROLE_ADMIN,  # Cargo de administração.
    ROLE_BUDGET,  # Cargo de orçamento.
    ROLE_STOCK,  # Cargo de estoque.
    usuario_tem_cargo,  # Verifica os grupos do usuário atual.
)


def user_roles(request):  # Prepara indicadores de cargo para os templates.
    user = request.user  # Obtém o usuário associado à requisição.
    return {  # Disponibiliza os cargos em variáveis de contexto.
        'is_stock_employee': usuario_tem_cargo(user, ROLE_STOCK),  # Indica acesso à área de estoque.
        'is_budget_employee': usuario_tem_cargo(user, ROLE_BUDGET),  # Indica acesso à área de orçamento.
        'is_app_admin': usuario_tem_cargo(user, ROLE_ADMIN),  # Indica acesso administrativo.
    }
