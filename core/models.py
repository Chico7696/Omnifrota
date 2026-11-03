from django.core.exceptions import ValidationError  # Usada para rejeitar vínculos de equipamento inválidos.
from django.db import models, transaction  # Fornece campos ORM e transações atômicas.

from .storage import DeduplicatingImageStorage  # Reutiliza imagens com conteúdo duplicado.


image_storage = DeduplicatingImageStorage()  # Armazenamento compartilhado para imagens de peças.


class cargos(models.Model):  # Representa os cargos registrados no sistema.
    id_cargo = models.AutoField(primary_key=True)  # Identificador numérico do cargo.
    nome = models.CharField(max_length=30)  # Nome exibido para o cargo.
    permissoes = models.CharField(  # Categoria de permissões associada ao cargo.
        max_length=10,  # Limita o tamanho do valor armazenado.
        choices=[('admin', 'Administrador'), ('user', 'Usuário')]  # Restringe as categorias disponíveis.
    )

    def __str__(self):  # Define a representação textual do cargo.
        return self.nome  # Usa o nome como rótulo legível.


class fabricantes(models.Model):  # Armazena os dados de contato dos fabricantes.
    id_fabricante = models.AutoField(primary_key=True)  # Identificador numérico do fabricante.
      
    nome = models.CharField(max_length=30)  # Nome comercial do fabricante.
    cnpj = models.CharField(max_length=18)  # Documento nacional da empresa.
    contato_email = models.EmailField()  # Endereço de e-mail para contato.
    telefone = models.CharField(max_length=15)  # Telefone de contato.
    site = models.URLField()  # Página institucional do fabricante.
    endereco = models.CharField(max_length=100)  # Endereço cadastrado.

    def __str__(self):  # Define a representação textual do fabricante.
        return self.nome  # Usa o nome comercial como rótulo.


class pedidos(models.Model):  # Registra compras de peças e seu acompanhamento.
    id_pedido = models.AutoField(primary_key=True)  # Identificador numérico do pedido.
    id_peca = models.ForeignKey('pecas', on_delete=models.CASCADE)  # Peça solicitada.
    quantidade = models.IntegerField()  # Unidades incluídas no pedido.
    preco = models.DecimalField(max_digits=10, decimal_places=2)  # Preço unitário no pedido.
    valor_total = models.DecimalField(max_digits=10, decimal_places=2)  # Valor total calculado do pedido.
    data_entrega = models.DateField()  # Data estimada de entrega.
    id_fornecedor = models.ForeignKey('fornecedores', on_delete=models.CASCADE)  # Fornecedor responsável pelo pedido.
    id_fabricante = models.ForeignKey('fabricantes', on_delete=models.CASCADE)  # Fabricante da peça solicitada.
    id_funcionario = models.ForeignKey('funcionarios', on_delete=models.CASCADE, null=True, blank=True)  # Funcionário que registrou o pedido, se associado.
    data_criacao = models.DateTimeField(auto_now_add=True)  # Data e hora em que o registro foi criado.
    status = models.CharField(  # Etapa atual de acompanhamento do pedido.
        max_length=20,  # Limita o tamanho do status persistido.
        choices=[  # Define os estados aceitos pelo sistema.
            ('pendente', 'Pedido pendente'),  # Aguardando envio.
            ('enviado', 'Pedido foi enviado'),  # Enviado pelo fornecedor.
            ('em_rota', 'Pedido está em rota de entrega'),  # Em transporte.
            ('saiu_origem', 'Pedido saiu do local de origem'),  # Saiu da origem.
            ('entregue', 'Pedido entregue'),  # Entrega concluída.
        ],
        default='pendente',  # Inicia pedidos como pendentes.
    )

    def __str__(self):  # Define um rótulo legível para o pedido.
        return f"Pedido {self.id_pedido} - {self.get_status_display()}"  # Inclui o identificador e o status traduzido.


class fornecedores(models.Model):  # Armazena empresas fornecedoras de peças.
    id_fornecedor = models.AutoField(primary_key=True)  # Identificador numérico do fornecedor.
    nome = models.CharField(max_length=30)  # Nome curto para listagens.
    cnpj = models.CharField(max_length=18)  # Documento nacional da empresa.
    razao_social = models.CharField(max_length=100)  # Nome jurídico registrado.
    contato = models.CharField(max_length=30)  # Pessoa ou canal de contato.
    id_pedidos = models.ForeignKey(  # Mantém referência opcional a um pedido relacionado.
        'pedidos', on_delete=models.SET_NULL, null=True, blank=True  # Preserva o fornecedor se o pedido for removido.
    )
    endereco = models.CharField(max_length=100)  # Endereço do fornecedor.

    def __str__(self):  # Define a representação textual do fornecedor.
        return self.nome  # Usa o nome curto como rótulo.


class veiculos(models.Model):  # Armazena dados dos veículos usados na frota e nas previsões.
    id_veiculo = models.AutoField(primary_key=True)  # Identificador numérico do veículo.
    modelo = models.CharField(max_length=30)  # Modelo do veículo.
    peso = models.DecimalField(max_digits=10, decimal_places=2)  # Peso registrado do veículo.
    tipo = models.CharField(max_length=30)  # Categoria do veículo.
    funcionalidade = models.CharField(max_length=100)  # Uso ou função do veículo.
    id_fabricante = models.ForeignKey('fabricantes', on_delete=models.CASCADE)  # Fabricante associado.
    quilometragem = models.IntegerField(default=0)  # Quilometragem atual registrada.
    data_fabricacao = models.DateField()  # Data de fabricação do veículo.
    tempo_uso = models.IntegerField(help_text='Tempo de uso em meses')  # Tempo de uso em meses.
    manutencao = models.BooleanField(default=False)  # Indica se houve manutenção recente.
    data_manutencao = models.DateField(null=True, blank=True)  # Data opcional da manutenção mais recente.
    valor_manutencao = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)  # Custo opcional da manutenção.

    def __str__(self):  # Define a representação textual do veículo.
        return self.modelo  # Usa o modelo como rótulo.


class pecas(models.Model):  # Mantém o catálogo de peças e seus saldos.
    id_peca = models.AutoField(primary_key=True)  # Identificador numérico da peça.
    imagem = models.ImageField(  # Armazena uma imagem opcional da peça.
        upload_to='pecas/', storage=image_storage, null=True, blank=True  # Usa o armazenamento que deduplica arquivos.
    )
    nome = models.CharField(max_length=150, default='')  # Nome usado nas listagens.
    categoria = models.CharField(max_length=100, blank=True, default='')  # Categoria usada nos filtros.
    descricao = models.CharField(  # Descrição complementar da peça.
        max_length=255, blank=True, default='',  # Permite descrição vazia.
        help_text='Descrição / aplicação da peça'  # Orienta o preenchimento do campo.
    )
    preco = models.DecimalField(max_digits=10, decimal_places=2)  # Preço unitário da peça.
    fornecedor = models.ForeignKey('fornecedores', on_delete=models.CASCADE)  # Fornecedor atual da peça.
    peso = models.DecimalField(max_digits=10, decimal_places=2)  # Peso unitário da peça.
    id_veiculo = models.ForeignKey('veiculos', on_delete=models.CASCADE, null=True, blank=True)  # Veículo compatível, se informado.
    id_fabricante = models.ForeignKey('fabricantes', on_delete=models.CASCADE)  # Fabricante da peça.
    dependecia = models.BooleanField(default=False)  # Indica dependência ou requisito específico da peça.
    validade = models.DateField(null=True, blank=True)  # Data de validade opcional.
    data_entrada = models.DateField(auto_now_add=True)  # Data automática de cadastro da peça.
    data_saida = models.DateField(null=True, blank=True)  # Data da última saída, quando aplicável.
    quantidade = models.IntegerField(default=0)  # Saldo atual em unidades.

    def __str__(self):  # Define a representação textual da peça.
        return self.nome or self.descricao  # Usa a descrição como alternativa ao nome vazio.

    def _schedule_image_cleanup(self, image_name, using):  # Agenda a remoção segura de uma imagem antiga.
        def delete_if_unused():  # Confere se algum registro ainda referencia o arquivo.
            if not type(self).objects.using(using).filter(imagem=image_name).exists():  # Busca referências no banco usado.
                self._meta.get_field('imagem').storage.delete(image_name)  # Remove o arquivo sem referência.

        transaction.on_commit(delete_if_unused, using=using)  # Só executa a limpeza após confirmar a transação.

    def save(self, *args, **kwargs):  # Salva a peça e agenda limpeza de uma imagem substituída.
        update_fields = kwargs.get('update_fields')  # Obtém os campos que serão atualizados, se limitados.
        updates_image = update_fields is None or 'imagem' in update_fields  # Verifica se a imagem participa da gravação.
        previous_image_name = None  # Inicializa a referência à imagem já armazenada.
        if self.pk and updates_image:  # Consulta o arquivo anterior somente em atualizações relevantes.
            previous_image_name = (  # Captura o nome do arquivo antes de salvar a nova versão.
                type(self).objects.using(self._state.db)  # Usa a conexão associada à instância.
                .filter(pk=self.pk)  # Limita a consulta ao registro atual.
                .values_list('imagem', flat=True)  # Lê apenas o nome do campo de imagem.
                .first()  # Retorna o nome anterior ou None.
            )

        result = super().save(*args, **kwargs)  # Persiste a instância pelo comportamento padrão do Django.
        new_image_name = self.imagem.name if self.imagem else None  # Obtém o arquivo que ficou associado após salvar.
        if previous_image_name and previous_image_name != new_image_name:  # Detecta a substituição de arquivo.
            self._schedule_image_cleanup(previous_image_name, self._state.db)  # Agenda a remoção do arquivo anterior.
        return result  # Preserva o retorno original do método save.

    def delete(self, *args, **kwargs):  # Exclui a peça e limpa sua imagem se não houver outros usos.
        image_name = self.imagem.name if self.imagem else None  # Guarda o arquivo antes de excluir o registro.
        using = kwargs.get('using') or self._state.db  # Identifica a conexão usada pela operação.
        result = super().delete(*args, **kwargs)  # Remove o registro pelo comportamento padrão do Django.
        if image_name:  # Agenda a limpeza somente quando existe uma imagem associada.
            self._schedule_image_cleanup(image_name, using)  # Preserva arquivos compartilhados por outros registros.
        return result  # Retorna o resultado original da exclusão.


class funcionarios(models.Model):
    id_funcionario = models.AutoField(primary_key=True)
    nome = models.CharField(max_length=30)
    setor = models.CharField(max_length=30)
    id_cargo = models.ForeignKey('cargos', on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return self.nome


class equipamentos(models.Model):
    id_equipamento = models.AutoField(primary_key=True)
    nome = models.CharField(max_length=30)
    funcao = models.CharField(max_length=100)
    status = models.CharField(
        max_length=20,
        choices=[('disponivel', 'Disponível'), ('em uso', 'Em Uso'), ('manutencao', 'Manutenção')],
        default='disponivel',
    )
    id_peca = models.ForeignKey('pecas', on_delete=models.CASCADE)

    def __str__(self):
        return self.nome


class estoque(models.Model):
    id_estoque = models.AutoField(primary_key=True)
    quantidade = models.IntegerField()
    quantidade_saida = models.PositiveIntegerField(default=0)
    data_entrada = models.DateField(auto_now_add=True)
    data_saida = models.DateField(null=True, blank=True)
    id_peca = models.ForeignKey('pecas', on_delete=models.CASCADE)
    id_fornecedor = models.ForeignKey('fornecedores', on_delete=models.CASCADE)
    id_equipamento = models.ForeignKey('equipamentos', on_delete=models.SET_NULL, null=True, blank=True)
    id_funcionario = models.ForeignKey('funcionarios', on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"Estoque {self.id_estoque} - {self.id_peca}"


class ordem_servico(models.Model):
    """Representa um 'Chamado' aberto na tela Chamados do wireframe."""
    id_servico = models.AutoField(primary_key=True)
    solicitante = models.CharField(max_length=100)
    email = models.EmailField()
    telefone = models.CharField(max_length=20)
    local = models.CharField(max_length=100, blank=True, default='')
    id_veiculo = models.ForeignKey('veiculos', on_delete=models.SET_NULL, null=True, blank=True)
    id_peca = models.ForeignKey('pecas', on_delete=models.CASCADE)
    data_abertura = models.DateField(auto_now_add=True)
    status = models.CharField(
        max_length=20,
        choices=[('aberta', 'Aberta'), ('em andamento', 'Em Andamento'), ('concluido', 'Concluído')],
        default='aberta',
    )
    id_funcionario = models.ForeignKey('funcionarios', on_delete=models.SET_NULL, null=True, blank=True)
    equipamentos = models.ForeignKey('equipamentos', on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"Chamado {self.id_servico} - {self.solicitante} ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        equipamento_anterior_id = None
        if self.pk:
            equipamento_anterior_id = (
                type(self).objects.filter(pk=self.pk)
                .values_list('equipamentos_id', flat=True)
                .first()
            )

        with transaction.atomic():
            equipamento = None
            if self.equipamentos_id:
                equipamento = equipamentos.objects.select_for_update().get(pk=self.equipamentos_id)
                chamado_ativo = type(self).objects.filter(
                    equipamentos_id=self.equipamentos_id,
                    status__in=['aberta', 'em andamento'],
                ).exclude(pk=self.pk).exists()
                if chamado_ativo and self.status in ['aberta', 'em andamento']:
                    raise ValidationError('Este equipamento já está vinculado a um chamado ativo.')
                if (
                    self.status in ['aberta', 'em andamento']
                    and equipamento_anterior_id != self.equipamentos_id
                    and equipamento.status != 'disponivel'
                ):
                    raise ValidationError('Este equipamento não está disponível para uma nova requisição.')

            super().save(*args, **kwargs)

            if equipamento_anterior_id and equipamento_anterior_id != self.equipamentos_id:
                equipamento_anterior = equipamentos.objects.select_for_update().get(pk=equipamento_anterior_id)
                if not type(self).objects.filter(
                    equipamentos_id=equipamento_anterior_id,
                    status__in=['aberta', 'em andamento'],
                ).exists():
                    equipamento_anterior.status = 'disponivel'
                    equipamento_anterior.save(update_fields=['status'])

            if equipamento:
                status_equipamento = 'em uso' if self.status in ['aberta', 'em andamento'] else 'disponivel'
                if equipamento.status != status_equipamento:
                    equipamento.status = status_equipamento
                    equipamento.save(update_fields=['status'])

    def delete(self, *args, **kwargs):
        equipamento_id = self.equipamentos_id
        with transaction.atomic():
            if equipamento_id:
                equipamento = equipamentos.objects.select_for_update().get(pk=equipamento_id)
            resultado = super().delete(*args, **kwargs)
            if equipamento_id and not type(self).objects.filter(
                equipamentos_id=equipamento_id,
                status__in=['aberta', 'em andamento'],
            ).exists():
                equipamento.status = 'disponivel'
                equipamento.save(update_fields=['status'])
        return resultado


class orcamento_ia(models.Model):
    id_orcamento = models.AutoField(primary_key=True)
    id_veiculo = models.ForeignKey('veiculos', on_delete=models.CASCADE, null=True, blank=True)
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    data_orcamento = models.DateField(auto_now_add=True)
    data_predicao = models.DateField()
    taxa_desvio = models.DecimalField(max_digits=5, decimal_places=4)
    previsao_mensal = models.JSONField(default=list, blank=True)
    status = models.CharField(
        max_length=20,
        choices=[('aprovado', 'Aprovado'), ('reprovado', 'Reprovado'), ('pendente', 'Pendente')],
        default='pendente',
    )

    def __str__(self):
        return f"Orçamento {self.id_orcamento} - {self.get_status_display()}"
