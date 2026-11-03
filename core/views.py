from datetime import date, timedelta
from decimal import Decimal
import json

from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Exists, F, OuterRef, Q
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.models import Group, User
from django.utils import timezone
from django.views.decorators.http import require_POST

from .access_control import (
    ROLE_ADMIN,
    ROLE_BUDGET,
    ROLE_STOCK,
    cargo_obrigatorio,
    garantir_grupos_de_cargos,
    usuario_tem_cargo,
)

from .models import (
    pecas, veiculos, fornecedores, fabricantes, pedidos,
    funcionarios, equipamentos, orcamento_ia, estoque, ordem_servico
)
from .forms import (
    pecasForm, veiculosForm, fornecedoresForm, fabricantesForm, pedidosForm,
    funcionariosForm, ordem_servicoForm, equipamentosForm, orcamento_iaForm,
    AtribuirCargoForm, ChamadoForm, OrcamentoIAForm, EntradaEstoqueForm,
    SaidaEstoqueForm,
)


def acesso_negado(request, exception=None):
    return render(
        request,
        'core/acesso_negado.html',
        {
            'error_code': 403,
            'error_title': 'Acesso negado',
            'error_message': 'Você não tem permissão para acessar esta página.',
        },
        status=403,
    )


def pagina_neymar(request):
    return render(request, 'core/neymar.html')


@login_required
def home(request):
    if usuario_tem_cargo(request.user, ROLE_BUDGET) and not usuario_tem_cargo(request.user, ROLE_STOCK):
        return redirect('orcamento_form')
    if usuario_tem_cargo(request.user, ROLE_STOCK):
        return redirect('lista_pecas')
    raise PermissionDenied


def login_usuario(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        usuario = authenticate(request, username=username, password=password)
        if usuario is not None:
            login(request, usuario)
            return redirect('home')
        else:
            messages.error(request, 'Usuário ou senha inválidos.')
            return redirect('login')
    return render(request, 'core/login.html')


def logout_usuario(request):
    logout(request)
    return redirect('login')


def registrar_usuario(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        email = request.POST.get('email')

        if User.objects.filter(username=username).exists():
            messages.error(request, 'Nome de usuário já existe.')
            return redirect('registrar')

        usuario = User.objects.create_user(username=username, password=password, email=email)
        usuario.save()

        funcionarios.objects.get_or_create(nome=username, setor='Sistema')
        garantir_grupos_de_cargos()
        grupo_estoque = Group.objects.get(name=ROLE_STOCK)
        usuario.groups.add(grupo_estoque)

        messages.success(request, 'Usuário registrado como funcionário de estoque.')
        return redirect('login')

    return render(request, 'core/registrar.html')


@cargo_obrigatorio(ROLE_ADMIN)
def gerenciar_cargos(request):
    if request.method == 'POST':
        form = AtribuirCargoForm(request.POST)
        if form.is_valid():
            usuario = form.cleaned_data['usuario']
            cargo = form.cleaned_data['cargo']
            eh_administrador = usuario.groups.filter(name=ROLE_ADMIN).exists()
            outro_administrador = (
                User.objects.filter(is_superuser=True).exists()
                or User.objects.filter(is_active=True, groups__name=ROLE_ADMIN)
                .exclude(pk=usuario.pk)
                .exists()
            )
            if eh_administrador and cargo != ROLE_ADMIN and not outro_administrador:
                form.add_error(
                    'cargo',
                    'Não é possível remover o cargo do último administrador.',
                )
            else:
                garantir_grupos_de_cargos()
                grupo = Group.objects.get(name=cargo)
                with transaction.atomic():
                    usuario.groups.set([grupo])
                    usuario.user_permissions.clear()
                    usuario.is_staff = cargo == ROLE_ADMIN
                    usuario.save(update_fields=['is_staff'])
                messages.success(request, f'Cargo de {usuario.username} atualizado.')
                return redirect('gerenciar_cargos')
    else:
        form = AtribuirCargoForm()

    usuarios = User.objects.filter(is_superuser=False).order_by('username')
    usuarios_com_cargo = [
        {
            'usuario': usuario,
            'cargo': (
                usuario.groups.filter(name__in=(ROLE_STOCK, ROLE_BUDGET, ROLE_ADMIN))
                .values_list('name', flat=True)
                .first()
                or 'Sem cargo'
            ),
        }
        for usuario in usuarios
    ]
    return render(request, 'core/gerenciar_cargos.html', {
        'form': form,
        'usuarios_com_cargo': usuarios_com_cargo,
    })


@cargo_obrigatorio(ROLE_ADMIN)
def resultados_testes(request):
    from django.conf import settings

    caminho_relatorio = settings.BASE_DIR / '.test-results' / 'latest.json'
    try:
        resultado = json.loads(caminho_relatorio.read_text(encoding='utf-8'))
    except FileNotFoundError:
        resultado = None
    except json.JSONDecodeError:
        resultado = None

    if resultado:
        for caso in resultado.get('casos', []):
            if not caso.get('explicacao'):
                nome_teste = caso.get('nome', '').split(' (', 1)[0]
                nome_teste = nome_teste.removeprefix('test_').replace('_', ' ')
                caso['explicacao'] = f'Verifica {nome_teste}.'

    return render(request, 'core/resultados_testes.html', {'resultado': resultado})


@cargo_obrigatorio(ROLE_STOCK)
@permission_required('core.add_pecas', login_url='/login/', raise_exception=True)
def adicionar_peca(request):
    if request.method == 'POST':
        form = pecasForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, 'Peça adicionada com sucesso!')
            return redirect('lista_pecas')
    else:
        form = pecasForm()
    return render(request, 'core/peca.html', {'form': form, 'modo': 'adicionar'})


@cargo_obrigatorio(ROLE_STOCK)
@permission_required('core.view_pecas', login_url='/login/', raise_exception=True)
def lista_pecas(request):
    busca = request.GET.get('q', '').strip()
    categoria = request.GET.get('categoria', '').strip()
    ordenar = request.GET.get('ordenar', 'nome')

    ordenacoes = {
        'nome': 'nome',
        'nome_desc': '-nome',
        'preco': 'preco',
        'preco_desc': '-preco',
        'quantidade': 'quantidade',
        'quantidade_desc': '-quantidade',
        'categoria': 'categoria',
        'categoria_desc': '-categoria',
    }

    pecas_queryset = pecas.objects.select_related('fornecedor', 'id_fabricante')
    if busca:
        pecas_queryset = pecas_queryset.filter(
            Q(nome__icontains=busca)
            | Q(categoria__icontains=busca)
            | Q(descricao__icontains=busca)
        )
    if categoria:
        pecas_queryset = pecas_queryset.filter(categoria=categoria)

    pecas_lista = pecas_queryset.order_by(ordenacoes.get(ordenar, 'nome'))
    categorias = (
        pecas.objects.exclude(categoria='')
        .values_list('categoria', flat=True)
        .distinct()
        .order_by('categoria')
    )
    contexto = {
        'pecas_lista': pecas_lista,
        'categorias': categorias,
        'busca': busca,
        'categoria_selecionada': categoria,
        'ordenar': ordenar if ordenar in ordenacoes else 'nome',
    }
    return render(request, 'core/lista_pecas.html', contexto)


@cargo_obrigatorio(ROLE_STOCK)
@permission_required('core.change_pecas', login_url='/login/', raise_exception=True)
def editar_peca(request, id):
    peca = get_object_or_404(pecas, id_peca=id)
    if request.method == 'POST':
        form = pecasForm(request.POST, request.FILES, instance=peca)
        if form.is_valid():
            form.save()
            messages.success(request, 'Peça atualizada com sucesso!')
            return redirect('lista_pecas')
    else:
        form = pecasForm(instance=peca)
    return render(request, 'core/peca.html', {'form': form, 'modo': 'editar', 'peca': peca})


@cargo_obrigatorio(ROLE_STOCK)
@permission_required('core.delete_pecas', login_url='/login/', raise_exception=True)
def excluir_peca(request, id):
    peca = get_object_or_404(pecas, id_peca=id)
    peca.delete()
    messages.success(request, 'Peça excluída com sucesso!')
    return redirect('lista_pecas')


@cargo_obrigatorio(ROLE_STOCK)
@permission_required('core.view_ordem_servico', login_url='/login/', raise_exception=True)
def chamados(request):
    if request.method == 'POST':
        form = ChamadoForm(request.POST)
        if form.is_valid():
            try:
                form.save()
            except ValidationError as error:
                form.add_error(None, error.messages)
            else:
                messages.success(request, 'Chamado enviado com sucesso!')
                return redirect('chamados')
    else:
        form = ChamadoForm()
    return render(request, 'core/chamados.html', {'form': form})

@cargo_obrigatorio(ROLE_STOCK)
@permission_required('core.view_equipamentos', login_url='/login/', raise_exception=True)
def equipamentos_view(request):
    chamados_ativos = ordem_servico.objects.filter(
        equipamentos_id=OuterRef('pk'),
        status__in=['aberta', 'em andamento'],
    )
    equipamentos_lista = (
        equipamentos.objects.select_related('id_peca')
        .annotate(chamado_ativo=Exists(chamados_ativos))
        .order_by('id_equipamento')
    )
    status_choices = dict(equipamentos._meta.get_field('status').choices)
    for equipamento in equipamentos_lista:
        equipamento.status_edicao = (
            'em uso'
            if equipamento.status == 'disponivel' and equipamento.chamado_ativo
            else equipamento.status
        )
        equipamento.status_exibicao = status_choices[equipamento.status_edicao]
    return render(request, 'core/equipamentos.html', {'equipamentos_lista': equipamentos_lista})


@cargo_obrigatorio(ROLE_ADMIN)
@permission_required('core.change_equipamentos', login_url='/login/', raise_exception=True)
@require_POST
def alterar_status_equipamento(request, id):
    status = request.POST.get('status')
    status_choices = dict(equipamentos._meta.get_field('status').choices)
    if status not in status_choices:
        messages.error(request, 'Selecione um status válido para o equipamento.')
        return redirect('equipamentos')

    with transaction.atomic():
        equipamento = get_object_or_404(
            equipamentos.objects.select_for_update(), id_equipamento=id
        )
        chamado_ativo = ordem_servico.objects.filter(
            equipamentos_id=equipamento.id_equipamento,
            status__in=['aberta', 'em andamento'],
        ).exists()
        if status == 'disponivel' and chamado_ativo:
            messages.error(
                request,
                'Não é possível liberar um equipamento vinculado a um chamado ativo.',
            )
        else:
            equipamento.status = status
            equipamento.save(update_fields=['status'])
            messages.success(request, 'Status do equipamento atualizado com sucesso.')
    return redirect('equipamentos')

@cargo_obrigatorio(ROLE_STOCK)
@permission_required('core.view_fornecedores', login_url='/login/', raise_exception=True)
def fornecedores_view(request):
    fornecedores_lista = fornecedores.objects.all().order_by('nome')
    return render(request, 'core/fornecedores.html', {'fornecedores_lista': fornecedores_lista})

@cargo_obrigatorio(ROLE_STOCK)
@permission_required('core.view_pedidos', login_url='/login/', raise_exception=True)
def pedidos_view(request):
    if request.method == 'POST':
        form = pedidosForm(request.POST)
        if form.is_valid():
            pedido = form.save(commit=False)
            pedido.id_funcionario = funcionarios.objects.filter(
                nome=request.user.username
            ).first()
            pedido.save()
            messages.success(request, 'Pedido realizado com sucesso!')
            return redirect('pedidos')
    else:
        form = pedidosForm()

    data_envio = timezone.now() - timedelta(days=3)
    pedidos.objects.filter(
        status='pendente', data_criacao__lte=data_envio
    ).update(status='enviado')
    pedidos_lista = (
        pedidos.objects.select_related('id_peca', 'id_fornecedor')
        .all()
        .order_by('id_pedido')
    )
    return render(request, 'core/pedidos.html', {
        'pedidos_lista': pedidos_lista,
        'form': form,
    })


@cargo_obrigatorio(ROLE_STOCK)
@permission_required('core.change_pedidos', login_url='/login/', raise_exception=True)
@require_POST
def marcar_pedido_entregue(request, id_pedido):
    pedido = get_object_or_404(pedidos, id_pedido=id_pedido)
    if pedido.status == 'enviado':
        pedido.status = 'entregue'
        pedido.save(update_fields=['status'])
        messages.success(request, 'Pedido marcado como entregue.')
    else:
        messages.warning(request, 'Somente pedidos enviados podem ser marcados como entregues.')
    return redirect('pedidos')


@cargo_obrigatorio(ROLE_STOCK)
@permission_required('core.view_pedidos', login_url='/login/', raise_exception=True)
def relatorios(request):
    movimentacoes = list(
        estoque.objects.select_related('id_peca').all().order_by('-id_estoque')[:20]
    )
    movimentacoes.reverse()
    for movimento in movimentacoes:
        movimento.quantidade_disponivel = max(
            movimento.quantidade - movimento.quantidade_saida, 0
        )
    orcamentos = []
    if usuario_tem_cargo(request.user, ROLE_ADMIN):
        orcamentos = list(
            orcamento_ia.objects.select_related('id_veiculo')
            .all()
            .order_by('-id_orcamento')[:20]
        )
        orcamentos.reverse()
    chamados_lista = list(
        ordem_servico.objects.select_related('id_peca', 'equipamentos')
        .all()
        .order_by('-id_servico')[:20]
    )
    chamados_lista.reverse()
    return render(request, 'core/relatorios.html', {
        'movimentacoes': movimentacoes,
        'orcamentos': orcamentos,
        'chamados_lista': chamados_lista,
        'form_entrada': EntradaEstoqueForm(),
    })


@cargo_obrigatorio(ROLE_STOCK)
@permission_required('core.add_estoque', login_url='/login/', raise_exception=True)
@require_POST
def registrar_entrada_estoque(request):
    form = EntradaEstoqueForm(request.POST)
    if not form.is_valid():
        mensagens = [erro for erros in form.errors.values() for erro in erros]
        messages.error(request, mensagens[0] if mensagens else 'Dados de entrada inválidos.')
        return redirect('relatorios')

    with transaction.atomic():
        peca = pecas.objects.select_for_update().get(
            pk=form.cleaned_data['peca'].pk
        )
        quantidade = form.cleaned_data['quantidade']
        peca.quantidade += quantidade
        peca.save(update_fields=['quantidade'])
        estoque.objects.create(
            quantidade=quantidade,
            id_peca=peca,
            id_fornecedor=form.cleaned_data['fornecedor'],
        )
    messages.success(request, 'Entrada registrada e saldo atualizado.')
    return redirect('relatorios')


@cargo_obrigatorio(ROLE_ADMIN)
@permission_required('core.change_ordem_servico', login_url='/login/', raise_exception=True)
@require_POST
def alterar_status_chamado(request, id):
    chamado = get_object_or_404(ordem_servico, id_servico=id)
    status = request.POST.get('status')
    status_choices = dict(ordem_servico._meta.get_field('status').choices)
    if status not in status_choices:
        messages.error(request, 'Selecione um status válido para o chamado.')
        return redirect('relatorios')

    deve_registrar_saida = status == 'concluido' and chamado.status != 'concluido'
    registrar_saida = False
    try:
        with transaction.atomic():
            chamado.status = status
            chamado.save()
            if deve_registrar_saida:
                peca = pecas.objects.select_for_update().get(
                    pk=chamado.id_peca_id
                )
                movimento = (
                    estoque.objects.select_for_update()
                    .filter(id_peca_id=chamado.id_peca_id)
                    .filter(quantidade_saida__lt=F('quantidade'))
                    .order_by('-id_estoque')
                    .first()
                )
                if movimento and peca.quantidade > 0:
                    movimento.quantidade_saida += 1
                    movimento.data_saida = timezone.localdate()
                    movimento.save(update_fields=['quantidade_saida', 'data_saida'])
                    peca.quantidade -= 1
                    peca.save(update_fields=['quantidade'])
                    registrar_saida = True
    except ValidationError as error:
        messages.error(request, error.messages[0])
    else:
        messages.success(request, 'Status do chamado atualizado com sucesso.')
        if deve_registrar_saida and not registrar_saida:
            messages.warning(
                request,
                'Chamado concluído, mas não há entrada de estoque sem data de saída para essa peça.',
            )
    return redirect('relatorios')


@cargo_obrigatorio(ROLE_STOCK)
@permission_required('core.change_estoque', login_url='/login/', raise_exception=True)
@require_POST
def registrar_saida_estoque(request, id):
    form = SaidaEstoqueForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Informe uma quantidade de saída válida.')
        return redirect('relatorios')

    quantidade = form.cleaned_data['quantidade']
    with transaction.atomic():
        movimento = get_object_or_404(estoque.objects.only('id_peca_id'), id_estoque=id)
        peca = pecas.objects.select_for_update().get(pk=movimento.id_peca_id)
        movimento = get_object_or_404(
            estoque.objects.select_for_update(), id_estoque=id
        )
        disponivel_no_movimento = movimento.quantidade - movimento.quantidade_saida
        if quantidade > disponivel_no_movimento:
            messages.error(request, 'A saída não pode exceder a quantidade deste movimento.')
        elif quantidade > peca.quantidade:
            messages.error(request, 'A saída não pode exceder o saldo atual da peça.')
        else:
            movimento.quantidade_saida += quantidade
            movimento.data_saida = timezone.localdate()
            movimento.save(update_fields=['quantidade_saida', 'data_saida'])
            peca.quantidade -= quantidade
            peca.save(update_fields=['quantidade'])
            messages.success(request, 'Saída registrada e saldo atualizado.')
    return redirect('relatorios')


MESES_PREVISAO = 6
ABREVIACOES_MESES = (
    'Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun',
    'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez',
)


def _rotulos_meses(quantidade, referencia=None):
    """Retorna os rótulos abreviados dos próximos ``quantidade`` meses."""
    referencia = referencia or date.today()
    return [
        ABREVIACOES_MESES[(referencia.month - 1 + deslocamento) % 12]
        for deslocamento in range(quantidade)
    ]


def _campo_predicao(dados):
    """Monta o dicionário de entrada esperado pela IA preditiva."""
    return {
        'qtd_veiculos': dados['qtd_veiculos'],
        'qtd_pecas': dados['qtd_pecas'],
        'ano_fabricacao': dados['ano_veiculo'],
        'peso_toneladas': float(dados['peso_toneladas'] or 0),
        'tipo_veiculo': int(dados['tipo_veiculo']),
        'funcionalidade': int(dados['funcionalidade']),
        'quilometragem': dados['quilometragem'],
        'tempo_uso_meses': dados['tempo_uso'],
        'manutencao_recente': int(dados['manutencao_recente']),
        # No CSV de treino este campo é um indicador (0/1); mantemos a mesma
        # escala para não introduzir valores fora da distribuição aprendida.
        'data_ultima_manutencao': (
            1 if dados.get('data_ultima_manutencao') else 0
        ),
        'valor_ultima_manutencao': float(dados['valor_ultima_manutencao'] or 0),
        'valor_pecas': float(dados['valor_pecas'] or 0),
    }


def _prever_orcamento(caso):
    """Usa o modelo de IA treinado para estimar o orçamento.

    Se o modelo ainda não existir, ele é treinado a partir do CSV antes da
    previsão, garantindo que a primeira requisição já funcione.
    """
    from orcamentos import ia_preditiva

    if not ia_preditiva.MODEL_PATH.exists():
        ia_preditiva.treinar()

    valor_previsto = Decimal(str(ia_preditiva.prever(caso))).quantize(Decimal('0.01'))
    if valor_previsto < 0:
        # O modelo pode extrapolar para valores negativos em casos extremos;
        # apenas evitamos orçamentos negativos, sem impor um piso artificial.
        valor_previsto = Decimal('0.00')

    # Desvio estimado a partir do erro real medido no treino do modelo.
    taxa_desvio = Decimal(str(ia_preditiva.carregar_taxa_desvio())).quantize(
        Decimal('0.0001')
    )

    # Projeção mensal decrescente usada no gráfico do orçamento.
    previsao = []
    valor_mes = valor_previsto
    for _ in range(MESES_PREVISAO):
        previsao.append(float(valor_mes.quantize(Decimal('0.01'))))
        valor_mes = valor_mes * Decimal('0.80')

    valor_total = sum(Decimal(str(v)) for v in previsao)
    return previsao, valor_total.quantize(Decimal('0.01')), taxa_desvio



@cargo_obrigatorio(ROLE_BUDGET)
@permission_required('core.view_orcamento_ia', login_url='/login/', raise_exception=True)
def orcamento_form_view(request):
    if request.method == 'POST':
        form = OrcamentoIAForm(request.POST)
        if form.is_valid():
            dados = form.cleaned_data
            # A quantidade e o valor das peças vêm do estoque real: derivamos
            # dos itens selecionados em vez de aceitar valores digitados.
            dados['qtd_pecas'] = form.quantidade_total_pecas
            dados['valor_pecas'] = form.valor_total_pecas
            fabricante_padrao = fabricantes.objects.first()

            if fabricante_padrao is None:
                veiculo = None
            else:
                veiculo = veiculos.objects.create(
                    modelo=dados['modelo'],
                    peso=dados['peso_toneladas'] or 0,
                    tipo=dados['tipo_veiculo'],
                    funcionalidade=dados['funcionalidade'],
                    id_fabricante=fabricante_padrao,
                    data_fabricacao=date(dados['ano_veiculo'], 1, 1),
                    tempo_uso=dados['tempo_uso'],
                    quilometragem=dados['quilometragem'],
                    manutencao=(dados['manutencao_recente'] == '1'),
                )

            if veiculo is not None:
                caso = _campo_predicao(dados)
                previsao, valor_total, taxa_desvio = _prever_orcamento(caso)
                orcamento = orcamento_ia.objects.create(
                    id_veiculo=veiculo,
                    valor=valor_total,
                    data_predicao=date.today() + timedelta(days=90),
                    taxa_desvio=taxa_desvio,
                    previsao_mensal=previsao,
                    status='pendente',
                )
                messages.success(request, 'Orçamento calculado com sucesso!')
                return redirect('orcamento_grafico', id_orcamento=orcamento.id_orcamento)
            else:
                messages.error(
                    request,
                    'Cadastre ao menos um Fabricante antes de gerar um orçamento.'
                )
    else:
        form = OrcamentoIAForm()
    return render(request, 'core/orcamento_form.html', {'form': form})


@cargo_obrigatorio(ROLE_BUDGET)
@permission_required('core.view_orcamento_ia', login_url='/login/', raise_exception=True)
def orcamento_grafico_view(request, id_orcamento=None):
    if id_orcamento:
        orcamento = get_object_or_404(orcamento_ia, id_orcamento=id_orcamento)
    else:
        orcamento = orcamento_ia.objects.order_by('-data_orcamento').first()

    meses = _rotulos_meses(MESES_PREVISAO)
    previsao = orcamento.previsao_mensal if orcamento else []
    return render(request, 'core/orcamento_grafico.html', {
        'orcamento': orcamento,
        'meses': meses,
        'previsao': previsao,
    })


@cargo_obrigatorio(ROLE_BUDGET)
@permission_required('core.view_orcamento_ia', login_url='/login/', raise_exception=True)
def orcamentos_historico_view(request):
    """Exibe todos os orçamentos anteriores em gráfico e permite baixar PDFs."""
    orcamentos = list(
        orcamento_ia.objects.select_related('id_veiculo').order_by('data_orcamento', 'id_orcamento')
    )
    meses = _rotulos_meses(MESES_PREVISAO)

    # Rótulos curtos por orçamento (data + veículo) para o eixo do gráfico.
    rotulos = []
    for orcamento in orcamentos:
        veiculo = orcamento.id_veiculo
        nome_veiculo = f"{veiculo.tipo} {veiculo.modelo}" if veiculo else 'N/D'
        rotulos.append(
            f"#{orcamento.id_orcamento} - {orcamento.data_orcamento:%d/%m/%Y} ({nome_veiculo})"
        )

    return render(request, 'core/orcamentos_historico.html', {
        'orcamentos': orcamentos,
        'rotulos': rotulos,
        'valores': [float(orcamento.valor) for orcamento in orcamentos],
        'meses': meses,
    })


@cargo_obrigatorio(ROLE_BUDGET)
@permission_required('core.view_orcamento_ia', login_url='/login/', raise_exception=True)
def orcamento_pdf_view(request, id_orcamento):
    """Gera e devolve o PDF com os dados de um orçamento específico."""
    from .pdf import gerar_pdf_orcamento

    orcamento = get_object_or_404(orcamento_ia, id_orcamento=id_orcamento)
    meses = _rotulos_meses(MESES_PREVISAO)
    conteudo = gerar_pdf_orcamento(orcamento, meses)

    resposta = HttpResponse(conteudo, content_type='application/pdf')
    resposta['Content-Disposition'] = (
        f'attachment; filename="orcamento_{orcamento.id_orcamento}.pdf"'
    )
    return resposta
    """Exibe todos os orçamentos anteriores em gráfico e permite baixar PDFs."""
    orcamentos = list(
        orcamento_ia.objects.select_related('id_veiculo').order_by('data_orcamento', 'id_orcamento')
    )
    meses = _rotulos_meses(MESES_PREVISAO)

    # Rótulos curtos por orçamento (data + veículo) para o eixo do gráfico.
    rotulos = []
    for orcamento in orcamentos:
        veiculo = orcamento.id_veiculo
        nome_veiculo = f"{veiculo.tipo} {veiculo.modelo}" if veiculo else 'N/D'
        rotulos.append(
            f"#{orcamento.id_orcamento} - {orcamento.data_orcamento:%d/%m/%Y} ({nome_veiculo})"
        )

    return render(request, 'core/orcamentos_historico.html', {
        'orcamentos': orcamentos,
        'rotulos': rotulos,
        'valores': [float(orcamento.valor) for orcamento in orcamentos],
        'meses': meses,
    })


@cargo_obrigatorio(ROLE_BUDGET)
@permission_required('core.view_orcamento_ia', login_url='/login/', raise_exception=True)
def orcamento_pdf_view(request, id_orcamento):
    """Gera e devolve o PDF com os dados de um orçamento específico."""
    from .pdf import gerar_pdf_orcamento

    orcamento = get_object_or_404(orcamento_ia, id_orcamento=id_orcamento)
    meses = _rotulos_meses(MESES_PREVISAO)
    conteudo = gerar_pdf_orcamento(orcamento, meses)

    resposta = HttpResponse(conteudo, content_type='application/pdf')
    resposta['Content-Disposition'] = (
        f'attachment; filename="orcamento_{orcamento.id_orcamento}.pdf"'
    )
    return resposta
