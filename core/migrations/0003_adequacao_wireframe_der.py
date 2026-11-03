import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_remove_funcionarios_id_cargo_delete_cargos'),
    ]

    operations = [
        # --- Cargo volta a existir, conforme o DER ---
        migrations.CreateModel(
            name='cargos',
            fields=[
                ('id_cargo', models.AutoField(primary_key=True, serialize=False)),
                ('nome', models.CharField(max_length=30)),
                ('permissoes', models.CharField(choices=[('admin', 'Administrador'), ('user', 'Usuário')], max_length=10)),
            ],
        ),
        migrations.AddField(
            model_name='funcionarios',
            name='id_cargo',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='core.cargos'),
        ),

        # --- Veículos: campo Quilometragem (DER) ---
        migrations.AddField(
            model_name='veiculos',
            name='quilometragem',
            field=models.IntegerField(default=0),
        ),
        migrations.AlterField(
            model_name='veiculos',
            name='manutencao',
            field=models.BooleanField(default=False),
        ),

        # --- Peças: campos exigidos pelas telas Estoque / Edição-Exclusão / Adicionar-Editar ---
        migrations.AddField(
            model_name='pecas',
            name='imagem',
            field=models.ImageField(blank=True, null=True, upload_to='pecas/'),
        ),
        migrations.AddField(
            model_name='pecas',
            name='nome',
            field=models.CharField(default='', max_length=150),
        ),
        migrations.AddField(
            model_name='pecas',
            name='categoria',
            field=models.CharField(blank=True, default='', max_length=100),
        ),
        migrations.AlterField(
            model_name='pecas',
            name='descricao',
            field=models.CharField(blank=True, default='', help_text='Descrição / aplicação da peça', max_length=255),
        ),
        migrations.AlterField(
            model_name='pecas',
            name='id_veiculo',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='core.veiculos'),
        ),
        migrations.AlterField(
            model_name='pecas',
            name='dependecia',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='pecas',
            name='validade',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='pecas',
            name='data_entrada',
            field=models.DateField(auto_now_add=True),
        ),
        migrations.AlterField(
            model_name='pecas',
            name='quantidade',
            field=models.IntegerField(default=0),
        ),

        # --- Estoque: relação com Equipamentos (DER) e datas automáticas ---
        migrations.AddField(
            model_name='estoque',
            name='id_equipamento',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='core.equipamentos'),
        ),
        migrations.AlterField(
            model_name='estoque',
            name='id_funcionario',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='core.funcionarios'),
        ),
        migrations.AlterField(
            model_name='estoque',
            name='data_entrada',
            field=models.DateField(auto_now_add=True),
        ),

        # --- Ordem de Serviço (tela Chamados): dados do solicitante ---
        migrations.AddField(
            model_name='ordem_servico',
            name='solicitante',
            field=models.CharField(default='', max_length=100),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='ordem_servico',
            name='email',
            field=models.EmailField(default='', max_length=254),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='ordem_servico',
            name='telefone',
            field=models.CharField(default='', max_length=20),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='ordem_servico',
            name='local',
            field=models.CharField(blank=True, default='', max_length=100),
        ),
        migrations.AlterField(
            model_name='ordem_servico',
            name='data_abertura',
            field=models.DateField(auto_now_add=True),
        ),
        migrations.AlterField(
            model_name='ordem_servico',
            name='status',
            field=models.CharField(choices=[('aberta', 'Aberta'), ('em andamento', 'Em Andamento'), ('concluido', 'Concluído')], default='aberta', max_length=20),
        ),
        migrations.AlterField(
            model_name='ordem_servico',
            name='id_veiculo',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='core.veiculos'),
        ),
        migrations.AlterField(
            model_name='ordem_servico',
            name='id_funcionario',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='core.funcionarios'),
        ),
        migrations.AlterField(
            model_name='ordem_servico',
            name='equipamentos',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='core.equipamentos'),
        ),

        # --- Equipamentos: status com valor padrão ---
        migrations.AlterField(
            model_name='equipamentos',
            name='status',
            field=models.CharField(choices=[('disponivel', 'Disponível'), ('em uso', 'Em Uso'), ('manutencao', 'Manutenção')], default='disponivel', max_length=20),
        ),

        # --- Pedidos: status compatível com a tela Pedidos do wireframe ---
        migrations.AlterField(
            model_name='pedidos',
            name='status',
            field=models.CharField(choices=[('pendente', 'Pedido pendente'), ('enviado', 'Pedido foi enviado'), ('em_rota', 'Pedido está em rota de entrega'), ('saiu_origem', 'Pedido saiu do local de origem'), ('entregue', 'Pedido entregue')], default='pendente', max_length=20),
        ),
        migrations.AlterField(
            model_name='pedidos',
            name='id_funcionario',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='core.funcionarios'),
        ),

        # --- Fornecedores: pedido associado é opcional ---
        migrations.AlterField(
            model_name='fornecedores',
            name='id_pedidos',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='core.pedidos'),
        ),

        # --- Orçamento IA: vínculo com o veículo simulado + série mensal para o gráfico ---
        migrations.AddField(
            model_name='orcamento_ia',
            name='id_veiculo',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='core.veiculos'),
        ),
        migrations.AddField(
            model_name='orcamento_ia',
            name='previsao_mensal',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AlterField(
            model_name='orcamento_ia',
            name='data_orcamento',
            field=models.DateField(auto_now_add=True),
        ),
        migrations.AlterField(
            model_name='orcamento_ia',
            name='status',
            field=models.CharField(choices=[('aprovado', 'Aprovado'), ('reprovado', 'Reprovado'), ('pendente', 'Pendente')], default='pendente', max_length=20),
        ),
    ]
