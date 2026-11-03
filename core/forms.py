from django import forms
from django.forms import ModelForm
from django.contrib.auth.models import User
from .access_control import ROLE_ADMIN, ROLE_BUDGET, ROLE_STOCK
from .models import (
    pecas, veiculos, fornecedores, fabricantes, pedidos,
    funcionarios, ordem_servico, equipamentos, orcamento_ia,
)


class AtribuirCargoForm(forms.Form):
    usuario = forms.ModelChoiceField(
        label='Funcionário',
        queryset=User.objects.none(),
    )
    cargo = forms.ChoiceField(
        label='Cargo',
        choices=[
            (ROLE_STOCK, 'Funcionário de estoque'),
            (ROLE_BUDGET, 'Funcionário de orçamento'),
            (ROLE_ADMIN, 'Administrador'),
        ],
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['usuario'].queryset = User.objects.filter(
            is_superuser=False
        ).order_by('username')

# Tipos de veículo e funcionalidades esperados pela IA preditiva.
# Os rótulos viram as categorias que o modelo aprendeu no treino.
TIPOS_VEICULO = [('1', '1 - Leve'), ('2', '2 - Médio'), ('3', '3 - Pesado')]
FUNCIONALIDADES = [('1', '1 - Transporte'), ('2', '2 - Serviço'), ('3', '3 - Carga')]


class pecasForm(ModelForm):
    class Meta:
        model = pecas
        fields = [
            'imagem', 'nome', 'categoria', 'descricao',
            'fornecedor', 'quantidade', 'peso', 'validade', 'preco',
            'id_veiculo', 'id_fabricante',
        ]
        widgets = { 
            'imagem': forms.ClearableFileInput(attrs={'accept': 'image/*'}),
            'validade': forms.DateInput(attrs={'type': 'date'}),
            'descricao': forms.Textarea(attrs={'rows': 3}),
        }
        help_texts = {
            'imagem': 'Imagens iguais são reutilizadas automaticamente.',
        }
        labels = {
            'imagem': 'Imagem',
            'fornecedor': 'Fornecedor',
            'quantidade': 'Quantidade',
            'peso': 'Peso',
            'validade': 'Validade',
            'preco': 'Preço',
            'descricao': 'Descrição / Aplicação',
            'id_veiculo': 'Veículo compatível',
            'id_fabricante': 'Fabricante',
        }


class fornecedoresForm(ModelForm):
    class Meta:
        model = fornecedores
        fields = '__all__'


class veiculosForm(ModelForm):
    class Meta:
        model = veiculos
        fields = '__all__'
        widgets = {
            'data_fabricacao': forms.DateInput(attrs={'type': 'date'}),
            'data_manutencao': forms.DateInput(attrs={'type': 'date'}),
        }


class fabricantesForm(ModelForm):
    class Meta:
        model = fabricantes
        fields = '__all__'


class pedidosForm(ModelForm):
    quantidade = forms.IntegerField(
        label='Quantidade',
        min_value=1,
        help_text='Informe quantas unidades deseja pedir.',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['id_peca'].queryset = pecas.objects.order_by('nome')

    class Meta:
        model = pedidos
        fields = ['id_peca', 'quantidade', 'data_entrega']
        labels = {
            'id_peca': 'Peça',
            'data_entrega': 'Data prevista de entrega',
        }
        widgets = {
            'data_entrega': forms.DateInput(attrs={'type': 'date'}),
        }

    def save(self, commit=True):
        pedido = super().save(commit=False)
        pedido.preco = pedido.id_peca.preco
        pedido.valor_total = pedido.preco * pedido.quantidade
        pedido.id_fornecedor = pedido.id_peca.fornecedor
        pedido.id_fabricante = pedido.id_peca.id_fabricante
        if commit:
            pedido.save()
        return pedido


class funcionariosForm(ModelForm):
    class Meta:
        model = funcionarios
        fields = '__all__'


class ordem_servicoForm(ModelForm):
    class Meta:
        model = ordem_servico
        fields = '__all__'


class equipamentosForm(ModelForm):
    class Meta:
        model = equipamentos
        fields = '__all__'


class EntradaEstoqueForm(forms.Form):
    peca = forms.ModelChoiceField(
        label='Peça', queryset=pecas.objects.order_by('nome')
    )
    quantidade = forms.IntegerField(label='Quantidade', min_value=1)
    fornecedor = forms.ModelChoiceField(
        label='Fornecedor', queryset=fornecedores.objects.order_by('nome')
    )


class SaidaEstoqueForm(forms.Form):
    quantidade = forms.IntegerField(label='Quantidade retirada', min_value=1)


class orcamento_iaForm(ModelForm):
    class Meta:
        model = orcamento_ia
        fields = '__all__'


class ChamadoForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        chamados_ativos = ordem_servico.objects.filter(
            equipamentos_id__isnull=False,
            status__in=['aberta', 'em andamento'],
        ).values('equipamentos_id')
        self.fields['equipamentos'].queryset = (
            equipamentos.objects.filter(status='disponivel')
            .exclude(id_equipamento__in=chamados_ativos)
            .order_by('nome')
        )
        self.fields['equipamentos'].required = True
        self.fields['local'].required = True

    class Meta:
        model = ordem_servico
        fields = ['solicitante', 'email', 'telefone', 'id_peca', 'equipamentos', 'local']
        labels = {
            'solicitante': 'Solicitante',
            'id_peca': 'Peça',
            'email': 'E-mail',
            'telefone': 'Telefone',
            'equipamentos': 'Equipamento necessário',
            'local': 'Destino da peça',
        }
        widgets = {
            'local': forms.TextInput(attrs={'placeholder': 'Ex.: Oficina central'}),
            'telefone': forms.TextInput(attrs={'placeholder': '(12) 34567-8910'}),
        }

    def clean_local(self):
        return self.cleaned_data['local'].strip()


class OrcamentoIAForm(forms.Form):
    """Coleta os campos que o modelo de IA preditiva usa para a previsão.

    Os nomes dos campos espelham as variáveis de entrada de
    ``orcamentos.ia_preditiva`` para que a previsão seja direta.

    A peça é escolhida num menu suspenso a partir do estoque real do sistema e
    a quantidade usada é informada ao lado. A quantidade total e o valor total
    das peças (``qtd_pecas`` / ``valor_pecas``) são derivados dessa escolha, e
    não digitados manualmente.
    """

    veiculo = forms.CharField(label='Veículo', max_length=30)
    modelo = forms.CharField(label='Modelo', max_length=30)
    ano_veiculo = forms.IntegerField(label='Ano do Veículo', min_value=1980, max_value=2100)
    tempo_uso = forms.IntegerField(label='Tempo de Uso (meses)', min_value=0)
    quilometragem = forms.IntegerField(label='Quilometragem', min_value=0, initial=0)
    peso_toneladas = forms.DecimalField(
        label='Peso (toneladas)', min_value=0, max_digits=8, decimal_places=2, initial=0
    )
    qtd_veiculos = forms.IntegerField(label='Quantidade de Veículos', min_value=1, initial=1)
    peca = forms.ModelChoiceField(
        label='Peça',
        queryset=pecas.objects.all().order_by('nome'),
        required=False,
        empty_label='Selecione uma peça...',
        help_text='Selecione a peça do estoque que será usada no orçamento.',
    )
    quantidade_utilizada = forms.IntegerField(
        label='Quantidade utilizada',
        min_value=1,
        initial=1,
        required=False,
        help_text='Quantas unidades dessa peça serão usadas.',
    )
    tipo_veiculo = forms.ChoiceField(label='Tipo de Veículo', choices=TIPOS_VEICULO)
    funcionalidade = forms.ChoiceField(label='Funcionalidade', choices=FUNCIONALIDADES)
    manutencao_recente = forms.ChoiceField(
        label='Fez Manutenção Recente',
        choices=[('1', 'Sim'), ('0', 'Não')],
        widget=forms.RadioSelect,
        initial='1',
    )
    data_ultima_manutencao = forms.DateField(
        label='Data da Última Manutenção',
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
    )
    valor_ultima_manutencao = forms.DecimalField(
        label='Valor da Última Manutenção (R$)',
        min_value=0, max_digits=10, decimal_places=2, initial=0,
    )

    def clean(self):
        dados = super().clean()
        peca = dados.get('peca')
        quantidade = dados.get('quantidade_utilizada')
        if peca and quantidade and quantidade > peca.quantidade:
            self.add_error(
                'quantidade_utilizada',
                f'Quantidade indisponível em estoque ({peca.quantidade} un. disponíveis).',
            )
        return dados

    @property
    def quantidade_total_pecas(self):
        """Quantidade usada da peça selecionada."""
        peca = self.cleaned_data.get('peca')
        if not peca:
            return 0
        return self.cleaned_data.get('quantidade_utilizada') or 0

    @property
    def valor_total_pecas(self):
        """Valor somado (preço x quantidade usada) da peça selecionada."""
        peca = self.cleaned_data.get('peca')
        if not peca:
            return 0
        return peca.preco * self.quantidade_total_pecas
