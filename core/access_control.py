from functools import wraps  # Preserva metadados das views envolvidas pelo decorador.

from django.contrib.auth import get_user_model  # Obtém o modelo de usuário configurado no projeto.
from django.contrib.auth.decorators import login_required  # Exige uma sessão autenticada.
from django.contrib.auth.models import Group, Permission  # Gerencia grupos e permissões do Django.
from django.core.exceptions import PermissionDenied  # Sinaliza acesso proibido.


ROLE_STOCK = 'Estoque'  # Nome do grupo responsável pelo estoque.
ROLE_BUDGET = 'Orçamento'  # Nome do grupo responsável por orçamentos.
ROLE_ADMIN = 'Administrador'  # Nome do grupo administrativo.
ROLE_NAMES = (ROLE_STOCK, ROLE_BUDGET, ROLE_ADMIN)  # Cargos reconhecidos pela aplicação.

STOCK_MODELS = (  # Modelos cujas permissões são atribuídas ao grupo de estoque.
    'pecas',  # Cadastro de peças.
    'estoque',  # Movimentações de estoque.
    'equipamentos',  # Equipamentos da frota.
    'fornecedores',  # Cadastro de fornecedores.
    'fabricantes',  # Cadastro de fabricantes.
    'pedidos',  # Pedidos de peças.
    'ordem_servico',  # Chamados de serviço.
)


def usuario_tem_cargo(user, role):  # Verifica se o usuário autenticado possui o cargo solicitado.
    return user.is_authenticated and (  # Usuários anônimos não recebem acesso por grupo.
        user.is_superuser  # Superusuários ignoram a verificação de cargo.
        or user.groups.filter(name__in=(ROLE_ADMIN, role)).exists()  # Administradores também podem acessar a área.
    )


def cargo_obrigatorio(role):  # Cria um decorador que protege uma view por cargo.
    def decorar_view(view):  # Recebe a view que será protegida.
        @login_required(login_url='/login/')  # Redireciona usuários não autenticados ao login.
        @wraps(view)  # Mantém o nome e os metadados originais da view.
        def executar_view(request, *args, **kwargs):  # Intercepta a requisição antes da view.
            if not usuario_tem_cargo(request.user, role):  # Confere o cargo do usuário atual.
                raise PermissionDenied  # Interrompe a requisição quando o cargo não é permitido.
            return view(request, *args, **kwargs)  # Continua para a view protegida.

        return executar_view  # Devolve a versão protegida da view.

    return decorar_view  # Devolve o decorador configurado com o cargo.


def garantir_grupos_de_cargos():  # Cria grupos e sincroniza as permissões do aplicativo.
    stock_permissions = Permission.objects.filter(  # Seleciona permissões dos modelos de estoque.
        content_type__app_label='core',  # Limita a consulta ao aplicativo atual.
        content_type__model__in=STOCK_MODELS,  # Inclui os modelos listados para o grupo.
    )
    budget_permissions = Permission.objects.filter(  # Seleciona as permissões necessárias à área de orçamento.
        content_type__app_label='core',  # Limita a consulta ao aplicativo atual.
        codename__in=(  # Restringe o grupo aos recursos usados pela previsão.
            'view_orcamento_ia',  # Permite consultar orçamentos.
            'add_orcamento_ia',  # Permite criar orçamentos.
            'view_pecas',  # Permite consultar peças selecionáveis.
            'view_veiculos',  # Permite consultar veículos.
            'add_veiculos',  # Permite registrar o veículo associado à previsão.
        ),
    )
    admin_permissions = Permission.objects.filter(content_type__app_label='core')  # Seleciona todas as permissões do app para administradores.

    for name, permissions in (  # Associa cada cargo ao conjunto de permissões correspondente.
        (ROLE_STOCK, stock_permissions),  # Permissões de estoque.
        (ROLE_BUDGET, budget_permissions),  # Permissões de orçamento.
        (ROLE_ADMIN, admin_permissions),  # Permissões administrativas.
    ):
        group, _ = Group.objects.get_or_create(name=name)  # Reutiliza o grupo ou cria um ausente.
        group.permissions.set(permissions)  # Substitui permissões antigas pelas atuais.

    # Contas existentes sem uma função de aplicação definida mantêm o acesso como
    # funcionários padrão; superusuários continuam a ignorar as verificações de função.
    stock_group = Group.objects.get(name=ROLE_STOCK)  # Obtém o grupo padrão de estoque.
    user_model = get_user_model()  # Usa o modelo de usuário configurado no projeto.
    for user in user_model.objects.filter(is_superuser=False).exclude(  # Localiza contas sem cargo de aplicação.
        groups__name__in=ROLE_NAMES  # Exclui usuários já associados a um dos cargos conhecidos.
    ).distinct():
        user.groups.add(stock_group)  # Atribui o grupo padrão às contas sem cargo.


def configurar_grupos_de_cargos(sender, **kwargs):  # Sinal chamado pelo Django após uma migração.
    if sender.label == 'core':  # Executa a sincronização somente para este aplicativo.
        garantir_grupos_de_cargos()  # Cria os grupos e atualiza suas permissões.
