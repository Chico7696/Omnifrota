from datetime import timedelta
from datetime import date
from decimal import Decimal
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import HttpResponse
from django.template import TemplateDoesNotExist, TemplateSyntaxError
from django.test import TestCase, Client, RequestFactory, SimpleTestCase, override_settings  # Importa ferramentas para criar e executar testes e simular acessos ao site.
from django.urls import reverse  # Permite encontrar a URL de uma página pelo nome da rota.
from django.contrib.auth.models import AnonymousUser, Group, User  # Importa os modelos de usuários e grupos de permissões do Django.
from django.utils import timezone

from .access_control import ROLE_ADMIN, ROLE_BUDGET, ROLE_STOCK  # Importa as constantes que representam os cargos do sistema.
from .forms import ChamadoForm, OrcamentoIAForm, pedidosForm
from .middleware import ErrorPageMiddleware
from .models import (
    equipamentos, estoque, fabricantes, fornecedores, funcionarios,
    ordem_servico, orcamento_ia, pecas, pedidos, veiculos,
)


class ErrorPageMiddlewareTest(SimpleTestCase):
    def setUp(self):
        self.request = RequestFactory().get('/pagina-inexistente/')
        self.request.user = AnonymousUser()
        self.middleware = ErrorPageMiddleware(lambda request: HttpResponse())

    def test_pagina_inexistente_exibe_tela_de_erro(self):
        response = self.client.get('/pagina-inexistente/')

        self.assertEqual(response.status_code, 404)
        self.assertContains(response, 'Página não encontrada', status_code=404)
        self.assertContains(response, 'Retornar à página de login', status_code=404)

    def test_erro_de_template_exibe_tela_de_erro(self):
        for erro in (
            TemplateDoesNotExist('template_inexistente.html'),
            TemplateSyntaxError('Sintaxe inválida no template'),
        ):
            with self.subTest(erro=type(erro).__name__):
                response = self.middleware.process_exception(self.request, erro)

                self.assertEqual(response.status_code, 500)
                self.assertContains(response, 'Erro ao carregar a página', status_code=500)
                self.assertContains(response, 'Retornar à página de login', status_code=500)


class ImagensPecasTest(TestCase):  # Testa o armazenamento, a reutilização e a exclusão de imagens das peças.
    def setUp(self):
        self.media_dir = tempfile.TemporaryDirectory()  # Cria um diretório temporário para armazenar as imagens.
        self.addCleanup(self.media_dir.cleanup)  # Remove o diretório temporário ao final dos testes.
        media_override = override_settings(MEDIA_ROOT=self.media_dir.name)  # Define o diretório temporário como local de armazenamento.
        media_override.enable()  # Ativa a configuração temporária.
        self.addCleanup(media_override.disable)  # Restaura a configuração original ao final dos testes.
        self.fabricante = fabricantes.objects.create(  # Cria o fabricante utilizado nos testes.
            nome='Fabricante', cnpj='00.000.000/0001-00',
            contato_email='fabricante@teste.com', telefone='111111111',
            site='https://fabricante.test', endereco='Rua A',
        )
        self.fornecedor = fornecedores.objects.create(  # Cria o fornecedor utilizado nos testes.
            nome='Fornecedor', cnpj='11.111.111/0001-11',
            razao_social='Fornecedor Teste', contato='Contato', endereco='Rua B',
        )

    @staticmethod
    def imagem(nome, conteudo):  # Cria um arquivo de imagem simulado para os testes.
        return SimpleUploadedFile(nome, conteudo, content_type='image/png')

    def nova_peca(self, nome, imagem):  # Cria uma peça com os dados informados.
        return pecas.objects.create(
            nome=nome,
            imagem=imagem,
            preco=10,
            fornecedor=self.fornecedor,
            peso=1,
            id_fabricante=self.fabricante,
        )

    def test_reutiliza_arquivo_de_imagem_identica(self):  # Verifica se imagens idênticas compartilham o mesmo arquivo.
        conteudo = b'mesmo conteudo de imagem'  # Define o conteúdo comum das imagens.
        primeira = self.nova_peca('Peça 1', self.imagem('peca.png', conteudo))  # Cria a primeira peça com imagem.
        segunda = self.nova_peca('Peça 2', self.imagem('outra.png', conteudo))  # Cria a segunda peça com o mesmo conteúdo.

        self.assertEqual(primeira.imagem.name, segunda.imagem.name)  # Verifica se as peças utilizam o mesmo arquivo.
        self.assertTrue(primeira.imagem.name.startswith('pecas/'))  # Confirma que a imagem está na pasta de peças.
        self.assertEqual(len(primeira.imagem.storage.listdir('pecas')[1]), 1)  # Verifica se existe apenas um arquivo na pasta.

    def test_substituicao_e_exclusao_preservam_imagem_em_uso(self):  # Verifica se imagens em uso são preservadas.
        imagem_compartilhada = b'imagem compartilhada'  # Define o conteúdo da imagem compartilhada.
        primeira = self.nova_peca('Peça 1', self.imagem('peca.png', imagem_compartilhada))  # Cria a primeira peça.
        segunda = self.nova_peca('Peça 2', self.imagem('peca.png', imagem_compartilhada))  # Cria a segunda peça com a mesma imagem.
        caminho_antigo = primeira.imagem.name  # Guarda o caminho original da imagem.

        with self.captureOnCommitCallbacks(execute=True):  # Executa os callbacks registrados após o commit.
            primeira.imagem = self.imagem('nova.png', b'nova imagem')  # Substitui a imagem da primeira peça.
            primeira.save()  # Salva a alteração da peça.
        self.assertTrue(segunda.imagem.storage.exists(caminho_antigo))  # Confirma que a imagem antiga continua em uso.

        with self.captureOnCommitCallbacks(execute=True):  # Executa os callbacks registrados durante a exclusão.
            segunda.delete()  # Exclui a segunda peça.
        self.assertFalse(segunda.imagem.storage.exists(caminho_antigo))  # Confirma que a imagem antiga foi removida.


class PedidosPecasTest(TestCase):
    def setUp(self):
        self.fabricante = fabricantes.objects.create(
            nome='Fabricante', cnpj='00.000.000/0001-00',
            contato_email='fabricante@teste.com', telefone='111111111',
            site='https://fabricante.test', endereco='Rua A',
        )
        self.fornecedor = fornecedores.objects.create(
            nome='Fornecedor', cnpj='11.111.111/0001-11',
            razao_social='Fornecedor Teste', contato='Contato', endereco='Rua B',
        )
        self.peca = pecas.objects.create(
            nome='Filtro de óleo', preco='12.50', fornecedor=self.fornecedor,
            peso=1, id_fabricante=self.fabricante,
        )
        self.usuario = User.objects.create_user(
            username='estoque_pedidos', password='senha123'
        )
        self.usuario.groups.add(Group.objects.get(name=ROLE_STOCK))
        funcionarios.objects.create(nome=self.usuario.username, setor='Estoque')
        self.client = Client()
        self.client.force_login(self.usuario)

    def test_pagina_exibe_formulario_para_fazer_pedido(self):
        response = self.client.get(reverse('pedidos'))

        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.context['form'], pedidosForm)
        self.assertContains(response, 'Fazer pedido de peças')

    def test_funcionario_pode_criar_pedido_de_peca(self):
        response = self.client.post(
            reverse('pedidos'),
            {
                'id_peca': self.peca.pk,
                'quantidade': 4,
                'data_entrega': '2026-11-15',
            },
        )

        self.assertRedirects(response, reverse('pedidos'))
        pedido = pedidos.objects.get()
        self.peca.refresh_from_db()
        self.assertEqual(pedido.id_peca, self.peca)
        self.assertEqual(pedido.quantidade, 4)
        self.assertEqual(pedido.preco, self.peca.preco)
        self.assertEqual(pedido.valor_total, 50)
        self.assertEqual(pedido.id_fornecedor, self.fornecedor)
        self.assertEqual(pedido.id_fabricante, self.fabricante)
        self.assertEqual(pedido.id_funcionario.nome, self.usuario.username)
        self.assertEqual(pedido.status, 'pendente')

    def test_pedido_criado_aparece_na_tabela_de_pedidos_realizados(self):
        response = self.client.post(
            reverse('pedidos'),
            {
                'id_peca': self.peca.pk,
                'quantidade': 4,
                'data_entrega': '2026-11-15',
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Filtro de óleo')
        self.assertContains(response, 'Fornecedor')
        self.assertContains(response, 'Pedido pendente')
        self.assertEqual(response.context['pedidos_lista'].count(), 1)

    def test_pedidos_sao_exibidos_em_ordem_crescente_de_id(self):
        pedido_com_id_menor = pedidos.objects.create(
            id_peca=self.peca,
            quantidade=1,
            preco=self.peca.preco,
            valor_total=self.peca.preco,
            data_entrega='2026-12-15',
            id_fornecedor=self.fornecedor,
            id_fabricante=self.fabricante,
        )
        pedido_com_id_maior = pedidos.objects.create(
            id_peca=self.peca,
            quantidade=1,
            preco=self.peca.preco,
            valor_total=self.peca.preco,
            data_entrega='2026-11-15',
            id_fornecedor=self.fornecedor,
            id_fabricante=self.fabricante,
        )

        response = self.client.get(reverse('pedidos'))
        pedidos_exibidos = list(response.context['pedidos_lista'])

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [pedido.id_pedido for pedido in pedidos_exibidos],
            [pedido_com_id_menor.id_pedido, pedido_com_id_maior.id_pedido],
        )

    def test_pedido_enviado_pode_ser_marcado_como_entregue(self):
        pedido = pedidos.objects.create(
            id_peca=self.peca,
            quantidade=2,
            preco=self.peca.preco,
            valor_total=25,
            data_entrega='2026-11-15',
            id_fornecedor=self.fornecedor,
            id_fabricante=self.fabricante,
            status='enviado',
        )

        response = self.client.post(
            reverse('marcar_pedido_entregue', args=[pedido.id_pedido])
        )

        self.assertRedirects(response, reverse('pedidos'))
        pedido.refresh_from_db()
        self.assertEqual(pedido.status, 'entregue')

    def test_pedido_pendente_nao_pode_ser_marcado_como_entregue(self):
        pedido = pedidos.objects.create(
            id_peca=self.peca,
            quantidade=2,
            preco=self.peca.preco,
            valor_total=25,
            data_entrega='2026-11-15',
            id_fornecedor=self.fornecedor,
            id_fabricante=self.fabricante,
            status='pendente',
        )

        response = self.client.post(
            reverse('marcar_pedido_entregue', args=[pedido.id_pedido])
        )

        self.assertRedirects(response, reverse('pedidos'))
        pedido.refresh_from_db()
        self.assertEqual(pedido.status, 'pendente')

    def test_pedido_pendente_muda_para_enviado_apos_tres_dias(self):
        agora = timezone.now()
        pedido_antigo = pedidos.objects.create(
            id_peca=self.peca,
            quantidade=2,
            preco=self.peca.preco,
            valor_total=25,
            data_entrega='2026-11-15',
            id_fornecedor=self.fornecedor,
            id_fabricante=self.fabricante,
            status='pendente',
        )
        pedido_recente = pedidos.objects.create(
            id_peca=self.peca,
            quantidade=1,
            preco=self.peca.preco,
            valor_total='12.50',
            data_entrega='2026-11-15',
            id_fornecedor=self.fornecedor,
            id_fabricante=self.fabricante,
            status='pendente',
        )
        pedidos.objects.filter(pk=pedido_antigo.pk).update(
            data_criacao=agora - timedelta(days=3)
        )

        with patch('core.views.timezone.now', return_value=agora):
            response = self.client.get(reverse('pedidos'))

        self.assertEqual(response.status_code, 200)
        pedido_antigo.refresh_from_db()
        pedido_recente.refresh_from_db()
        self.assertEqual(pedido_antigo.status, 'enviado')
        self.assertEqual(pedido_recente.status, 'pendente')

    def test_quantidade_invalida_nao_cria_pedido(self):
        response = self.client.post(
            reverse('pedidos'),
            {
                'id_peca': self.peca.pk,
                'quantidade': 0,
                'data_entrega': '2026-11-15',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'maior ou igual a 1')
        self.assertFalse(pedidos.objects.exists())


class PermissoesPorCargoTest(TestCase):  # Agrupa os testes de permissões e funcionalidades de cada cargo.

    def test_equipamento_disponivel_com_chamado_ativo_nao_pode_ser_selecionado(self):  # Verifica se equipamentos com chamados ativos são bloqueados.
        fabricante = fabricantes.objects.create(  # Cria o fabricante da peça.
            nome='Fabricante', cnpj='00.000.000/0001-00',
            contato_email='fabricante@teste.com', telefone='111111111',
            site='https://fabricante.test', endereco='Rua A',
        )
        fornecedor = fornecedores.objects.create(  # Cria o fornecedor da peça.
            nome='Fornecedor', cnpj='11.111.111/0001-11',
            razao_social='Fornecedor Teste', contato='Contato', endereco='Rua B',
        )
        peca = pecas.objects.create(  # Cadastra a peça utilizada nos equipamentos.
            nome='Peça teste', preco=10, fornecedor=fornecedor,
            peso=1, id_fabricante=fabricante,
        )
        equipamento = equipamentos.objects.create(  # Cria o equipamento vinculado ao chamado.
            nome='Equipamento teste', funcao='Teste', id_peca=peca,
        )
        equipamento_livre = equipamentos.objects.create(  # Cria outro equipamento disponível para seleção.
            nome='Equipamento livre', funcao='Teste', id_peca=peca,
        )
        ordem_servico.objects.create(  # Cria um chamado associado ao primeiro equipamento.
            solicitante='Solicitante', email='solicitante@teste.com',
            telefone='111111111', id_peca=peca, equipamentos=equipamento,
        )
        equipamentos.objects.filter(pk=equipamento.pk).update(status='disponivel')  # Define o equipamento como disponível no banco.

        form = ChamadoForm()  # Instancia o formulário de chamados.

        self.assertFalse(form.fields['equipamentos'].queryset.filter(pk=equipamento.pk).exists())  # Confirma que o equipamento com chamado ativo não pode ser selecionado.
        self.assertTrue(form.fields['equipamentos'].queryset.filter(pk=equipamento_livre.pk).exists())  # Confirma que o equipamento livre pode ser selecionado.

    def test_administrador_altera_status_do_chamado_e_libera_equipamento(self):  # Verifica se concluir um chamado libera o equipamento.
        fabricante = fabricantes.objects.create(  # Cria o fabricante da peça.
            nome='Fabricante', cnpj='00.000.000/0001-00',
            contato_email='fabricante@teste.com', telefone='111111111',
            site='https://fabricante.test', endereco='Rua A',
        )
        fornecedor = fornecedores.objects.create(  # Cria o fornecedor da peça.
            nome='Fornecedor', cnpj='11.111.111/0001-11',
            razao_social='Fornecedor Teste', contato='Contato', endereco='Rua B',
        )
        peca = pecas.objects.create(  # Cadastra a peça utilizada no teste.
            nome='Peça teste', preco=10, fornecedor=fornecedor,
            peso=1, id_fabricante=fabricante, quantidade=1,
        )
        equipamento = equipamentos.objects.create(  # Cria o equipamento que será liberado.
            nome='Equipamento teste', funcao='Teste', id_peca=peca,
        )
        chamado = ordem_servico.objects.create(  # Cria o chamado vinculado ao equipamento.
            solicitante='Solicitante', email='solicitante@teste.com',
            telefone='111111111', id_peca=peca, equipamentos=equipamento,
        )
        movimento = estoque.objects.create(  # Registra uma movimentação de estoque.
            quantidade=1, id_peca=peca, id_fornecedor=fornecedor,
        )
        administrador = User.objects.create_user(username='admin_status', password='senha123')  # Cria o usuário administrador.
        administrador.groups.add(Group.objects.get(name=ROLE_ADMIN))  # Associa o usuário ao grupo de administradores.
        client = Client()  # Cria um cliente para simular as requisições HTTP.
        client.force_login(administrador)  # Autentica o administrador no cliente de teste.

        response = client.post(  # Envia a solicitação para concluir o chamado.
            reverse('alterar_status_chamado', args=[chamado.id_servico]),
            {'status': 'concluido'},
        )

        self.assertEqual(response.status_code, 302)  # Verifica se a operação redireciona após a conclusão.
        chamado.refresh_from_db()  # Atualiza os dados do chamado.
        equipamento.refresh_from_db()  # Atualiza os dados do equipamento.
        self.assertEqual(chamado.status, 'concluido')  # Confirma que o chamado foi concluído.
        self.assertEqual(equipamento.status, 'disponivel')  # Confirma que o equipamento foi liberado.
        movimento.refresh_from_db()  # Atualiza os dados da movimentação de estoque.
        self.assertEqual(movimento.data_saida, timezone.localdate())  # Verifica se a saída foi registrada na data atual.
        self.assertEqual(movimento.quantidade_saida, 1)
        peca.refresh_from_db()
        self.assertEqual(peca.quantidade, 0)

        client.post(
            reverse('alterar_status_chamado', args=[chamado.id_servico]),
            {'status': 'concluido'},
        )
        movimento.refresh_from_db()
        peca.refresh_from_db()
        self.assertEqual(movimento.quantidade_saida, 1)
        self.assertEqual(peca.quantidade, 0)

    def test_administrador_altera_status_manual_e_conclusao_libera_equipamento(self):  # Testa a saída de estoque e a alteração dos status.
        fabricante = fabricantes.objects.create(  # Cria o fabricante da peça.
            nome='Fabricante', cnpj='00.000.000/0001-00',
            contato_email='fabricante@teste.com', telefone='111111111',
            site='https://fabricante.test', endereco='Rua A',
        )
        fornecedor = fornecedores.objects.create(  # Cria o fornecedor da peça.
            nome='Fornecedor', cnpj='11.111.111/0001-11',
            razao_social='Fornecedor Teste', contato='Contato', endereco='Rua B',
        )
        peca = pecas.objects.create(  # Cadastra a peça associada ao equipamento.
            nome='Peça teste', preco=10, fornecedor=fornecedor,
            peso=1, id_fabricante=fabricante, quantidade=1,
        )
        equipamento = equipamentos.objects.create(  # Cria o equipamento que terá seu status alterado.
            nome='Equipamento teste', funcao='Teste', id_peca=peca,
        )
        chamado = ordem_servico.objects.create(  # Cria um chamado vinculado ao equipamento.
            solicitante='Solicitante', email='solicitante@teste.com',
            telefone='111111111', id_peca=peca, equipamentos=equipamento,
        )
        movimento = estoque.objects.create(  # Registra uma movimentação para testar a saída de estoque.
            quantidade=1, id_peca=peca, id_fornecedor=fornecedor,
        )
        administrador = User.objects.create_user(username='admin_equipamento', password='senha123')  # Cria o usuário administrador.
        administrador.groups.add(Group.objects.get(name=ROLE_ADMIN))  # Adiciona o usuário ao grupo de administradores.
        client = Client()  # Cria um cliente para simular as requisições.
        client.force_login(administrador)  # Autentica o administrador.

        response = client.post(  # Solicita o registro da saída do estoque.
            reverse('registrar_saida_estoque', args=[movimento.id_estoque]),
            {'quantidade': 1},
        )
        self.assertEqual(response.status_code, 302)  # Confirma que a operação redireciona.
        movimento.refresh_from_db()  # Atualiza os dados da movimentação.
        self.assertEqual(movimento.data_saida, timezone.localdate())  # Verifica se a saída foi registrada na data atual.
        self.assertEqual(movimento.quantidade_saida, 1)
        peca.refresh_from_db()
        self.assertEqual(peca.quantidade, 0)

        response = client.post(
            reverse('registrar_saida_estoque', args=[movimento.id_estoque]),
            {'quantidade': 1},
        )
        self.assertEqual(response.status_code, 302)
        movimento.refresh_from_db()
        peca.refresh_from_db()
        self.assertEqual(movimento.quantidade_saida, 1)
        self.assertEqual(peca.quantidade, 0)

        response = client.post(  # Solicita a alteração manual do status do equipamento.
            reverse('alterar_status_equipamento', args=[equipamento.id_equipamento]),
            {'status': 'manutencao'},
        )
        self.assertEqual(response.status_code, 302)  # Confirma que a alteração foi processada.
        equipamento.refresh_from_db()  # Atualiza os dados do equipamento.
        self.assertEqual(equipamento.status, 'manutencao')  # Verifica se o equipamento entrou em manutenção.

        response = client.post(  # Solicita a conclusão do chamado.
            reverse('alterar_status_chamado', args=[chamado.id_servico]),
            {'status': 'concluido'},
        )
        self.assertEqual(response.status_code, 302)  # Confirma que a conclusão foi processada.
        equipamento.refresh_from_db()  # Atualiza o equipamento após concluir o chamado.
        self.assertEqual(equipamento.status, 'disponivel')  # Confirma que o equipamento foi liberado.

    def test_registrar_entrada_soma_quantidade_ao_saldo(self):
        fabricante = fabricantes.objects.create(
            nome='Fabricante', cnpj='00.000.000/0001-00',
            contato_email='fabricante@teste.com', telefone='111111111',
            site='https://fabricante.test', endereco='Rua A',
        )
        fornecedor = fornecedores.objects.create(
            nome='Fornecedor', cnpj='11.111.111/0001-11',
            razao_social='Fornecedor Teste', contato='Contato', endereco='Rua B',
        )
        peca = pecas.objects.create(
            nome='Peça teste', preco=10, fornecedor=fornecedor,
            peso=1, id_fabricante=fabricante, quantidade=2,
        )
        administrador = User.objects.create_user(username='admin_entrada', password='senha123')
        administrador.groups.add(Group.objects.get(name=ROLE_ADMIN))
        client = Client()
        client.force_login(administrador)

        response = client.post(
            reverse('registrar_entrada_estoque'),
            {'peca': peca.pk, 'quantidade': 4, 'fornecedor': fornecedor.pk},
        )

        self.assertEqual(response.status_code, 302)
        peca.refresh_from_db()
        self.assertEqual(peca.quantidade, 6)
        movimento = estoque.objects.get(id_peca=peca)
        self.assertEqual(movimento.quantidade, 4)
        self.assertEqual(movimento.quantidade_saida, 0)

    def test_cadastro_publico_cria_funcionario_de_estoque(self):  # Verifica se o cadastro público cria um usuário do estoque.
        client = Client()  # Cria um cliente para simular o navegador.

        response = client.post(  # Simula o envio do formulário de cadastro.
            reverse('registrar'),  # Obtém a URL da rota de registro.
            {
                'username': 'novo_usuario',  # Define o nome do novo usuário.
                'email': 'novo@teste.com',  # Informa o e-mail do novo usuário.
                'password': 'senha123',  # Define a senha do novo usuário.
            },
            follow=False,  # Impede que o cliente siga automaticamente o redirecionamento.
        )

        self.assertEqual(response.status_code, 302)  # Verifica se o cadastro termina com um redirecionamento HTTP 302.
        usuario = User.objects.get(username='novo_usuario')  # Recupera o usuário criado no banco de dados.
        self.assertTrue(usuario.groups.filter(name=ROLE_STOCK).exists())  # Confirma que o usuário pertence ao grupo de estoque.
        self.assertTrue(usuario.has_perm('core.view_pecas'))  # Verifica se o usuário pode visualizar peças.
        self.assertTrue(usuario.has_perm('core.add_pecas'))  # Verifica se o usuário pode cadastrar peças.
        self.assertFalse(usuario.has_perm('core.view_orcamento_ia'))  # Confirma que o usuário não pode visualizar orçamentos de IA.

    def test_funcionario_de_estoque_nao_acessa_orcamentos_nem_menu(self):  # Verifica as restrições de acesso do funcionário de estoque.
        usuario = User.objects.create_user(username='estoque', password='senha123')  # Cria um usuário para o setor de estoque.
        usuario.groups.add(Group.objects.get(name=ROLE_STOCK))  # Associa o usuário ao grupo de estoque.
        client = Client()  # Cria um cliente para simular o navegador.
        client.force_login(usuario)  # Autentica o funcionário no sistema.

        estoque_response = client.get(reverse('lista_pecas'))  # Acessa a página de listagem de peças.
        self.assertEqual(estoque_response.status_code, 200)  # Confirma que a página de estoque está acessível.
        self.assertContains(estoque_response, 'Estoque')  # Verifica se a página apresenta o texto "Estoque".
        self.assertNotContains(estoque_response, 'Orçamentos')  # Confirma que o texto "Orçamentos" não aparece na página.
        acesso_negado = client.get(reverse('orcamento_form'))  # Tenta acessar uma área sem permissão.
        self.assertEqual(acesso_negado.status_code, 403)  # Verifica se o acesso aos orçamentos é proibido.
        self.assertTemplateUsed(acesso_negado, 'core/acesso_negado.html')
        self.assertContains(acesso_negado, reverse('login'), status_code=403)
        self.assertContains(acesso_negado, 'Retornar à página de login', status_code=403)
        self.assertEqual(client.get(reverse('gerenciar_cargos')).status_code, 403)  # Verifica se o gerenciamento de cargos é proibido.
        self.assertNotContains(client.get(reverse('relatorios')), 'Orçamentos')  # Confirma que os relatórios não exibem "Orçamentos".

    def test_funcionario_de_orcamento_nao_acessa_estoque(self):  # Verifica se o funcionário de orçamento não acessa o estoque.
        usuario = User.objects.create_user(username='orcamento', password='senha123')  # Cria um usuário do setor de orçamento.
        usuario.groups.add(Group.objects.get(name=ROLE_BUDGET))  # Associa o usuário ao grupo de orçamento.
        client = Client()  # Cria um cliente para simular o navegador.
        client.force_login(usuario)  # Autentica o funcionário no sistema.

        orcamento_response = client.get(reverse('orcamento_form'))  # Acessa o formulário de cadastro de orçamentos.
        self.assertEqual(orcamento_response.status_code, 200)  # Confirma que a página de orçamento está acessível.
        self.assertContains(orcamento_response, 'Orçamentos')  # Verifica se a página apresenta o texto "Orçamentos".
        self.assertContains(orcamento_response, 'Histórico de orçamentos')  # Confirma que o histórico de orçamentos aparece.
        self.assertNotContains(orcamento_response, 'Estoque')  # Verifica se a página não exibe o texto "Estoque".
        self.assertEqual(client.get(reverse('lista_pecas')).status_code, 403)  # Confirma que o acesso à listagem de peças é proibido.

    def test_administrador_acessa_estoque_orcamento_e_gerencia_cargos(self):  # Verifica o acesso do administrador às áreas principais.
        usuario = User.objects.create_user(username='admin_app', password='senha123')  # Cria o usuário administrador.
        usuario.groups.add(Group.objects.get(name=ROLE_ADMIN))  # Associa o usuário ao grupo de administradores.
        client = Client()  # Cria um cliente de teste.
        client.force_login(usuario)  # Autentica o administrador.

        for rota in (  # Percorre as rotas que devem estar disponíveis ao administrador.
            'lista_pecas',  # Página de listagem de peças.
            'adicionar_peca',  # Página de cadastro de peças.
            'pedidos',  # Página de pedidos.
            'chamados',  # Página de chamados.
            'relatorios',  # Página de relatórios.
            'fornecedores',  # Página de fornecedores.
            'equipamentos',  # Página de equipamentos.
            'orcamento_form',  # Página de cadastro de orçamentos.
            'orcamento_grafico',  # Página de gráficos de orçamentos.
            'orcamentos_historico',  # Página do histórico de orçamentos.
            'gerenciar_cargos',  # Página de gerenciamento de cargos.
        ):
            with self.subTest(rota=rota):  # Identifica individualmente a rota caso ocorra uma falha.
                self.assertEqual(client.get(reverse(rota)).status_code, 200)  # Verifica se o administrador pode acessar a rota.

    def test_administrador_pode_alterar_cargo_e_nao_remover_o_ultimo_admin(self):  # Testa a alteração de cargos e a proteção do último administrador.
        administrador = User.objects.create_user(username='admin_app', password='senha123')  # Cria o usuário administrador.
        administrador.groups.add(Group.objects.get(name=ROLE_ADMIN))  # Associa o administrador ao grupo correspondente.
        funcionario = User.objects.create_user(username='funcionario', password='senha123')  # Cria um funcionário para alterar o cargo.
        funcionario.groups.add(Group.objects.get(name=ROLE_STOCK))  # Define inicialmente o cargo de estoque.
        client = Client()  # Cria um cliente para simular as requisições.
        client.force_login(administrador)  # Autentica o administrador.

        response = client.post(  # Envia a solicitação de alteração do cargo do funcionário.
            reverse('gerenciar_cargos'),  # Obtém a URL de gerenciamento de cargos.
            {'usuario': funcionario.pk, 'cargo': ROLE_BUDGET},  # Informa o funcionário e o novo cargo de orçamento.
        )
        self.assertEqual(response.status_code, 302)  # Confirma que a alteração redireciona após ser processada.
        funcionario.refresh_from_db()  # Atualiza os dados do funcionário.
        self.assertEqual(list(funcionario.groups.values_list('name', flat=True)), [ROLE_BUDGET])  # Confirma que o funcionário possui somente o cargo de orçamento.
        self.assertFalse(funcionario.is_staff)  # Verifica que o funcionário não recebeu o status de membro da equipe administrativa do Django.

        response = client.post(  # Tenta remover o cargo do último administrador.
            reverse('gerenciar_cargos'),  # Obtém a URL de gerenciamento de cargos.
            {'usuario': administrador.pk, 'cargo': ROLE_STOCK},  # Solicita a alteração do administrador para o cargo de estoque.
        )
        self.assertEqual(response.status_code, 200)  # Confirma que a página é exibida novamente sem redirecionamento.
        self.assertContains(response, 'Não é possível remover o cargo do último administrador.')  # Verifica se a mensagem de proteção é exibida.

    def test_atribuicao_recria_grupo_ausente_com_permissoes(self):  # Verifica se um grupo ausente é recriado com suas permissões.
        administrador = User.objects.create_user(username='admin_app', password='senha123')  # Cria o usuário administrador.
        administrador.groups.add(Group.objects.get(name=ROLE_ADMIN))  # Associa o administrador ao grupo correspondente.
        funcionario = User.objects.create_user(username='funcionario', password='senha123')  # Cria o funcionário que receberá o cargo.
        Group.objects.filter(name=ROLE_BUDGET).delete()  # Exclui o grupo de orçamento para simular sua ausência.
        client = Client()  # Cria um cliente para simular as requisições.
        client.force_login(administrador)  # Autentica o administrador.

        response = client.post(  # Solicita a atribuição do cargo de orçamento.
            reverse('gerenciar_cargos'),  # Obtém a URL de gerenciamento de cargos.
            {'usuario': funcionario.pk, 'cargo': ROLE_BUDGET},  # Informa o funcionário e o cargo desejado.
        )

        self.assertEqual(response.status_code, 302)  # Confirma que a operação termina com um redirecionamento.
        funcionario.refresh_from_db()  # Atualiza os dados do funcionário.
        self.assertTrue(funcionario.groups.filter(name=ROLE_BUDGET).exists())  # Verifica se o grupo foi recriado e associado ao funcionário.
        self.assertTrue(funcionario.has_perm('core.view_orcamento_ia'))  # Confirma que o grupo recriado concede permissão para visualizar orçamentos de IA.


class ViewsSemCoberturaTest(TestCase):  # Agrupa testes das views e dos helpers ainda sem cobertura.
    def setUp(self):
        self.fabricante = fabricantes.objects.create(  # Cria o fabricante usado pelos testes.
            nome='Fabricante', cnpj='00.000.000/0001-00',
            contato_email='fabricante@teste.com', telefone='111111111',
            site='https://fabricante.test', endereco='Rua A',
        )
        self.fornecedor = fornecedores.objects.create(  # Cria o fornecedor usado pelos testes.
            nome='Fornecedor', cnpj='11.111.111/0001-11',
            razao_social='Fornecedor Teste', contato='Contato', endereco='Rua B',
        )

    def criar_usuario(self, nome, cargo):
        usuario = User.objects.create_user(username=nome, password='senha123')  # Cria o usuário autenticado no cenário.
        usuario.groups.add(Group.objects.get(name=cargo))  # Associa o usuário ao cargo informado.
        return usuario

    def criar_peca(self, nome='Peça teste', quantidade=5):
        return pecas.objects.create(  # Cria uma peça vinculada ao fabricante e fornecedor do teste.
            nome=nome, categoria='Filtros', descricao='Peça para teste',
            preco=Decimal('12.50'), fornecedor=self.fornecedor, peso=1,
            id_fabricante=self.fabricante, quantidade=quantidade,
        )

    def cliente_com_cargo(self, nome, cargo):
        client = Client()  # Cria o cliente HTTP para o cenário.
        client.force_login(self.criar_usuario(nome, cargo))  # Autentica o usuário com o cargo correspondente.
        return client

    def dados_orcamento(self, **alteracoes):
        dados = {  # Define valores válidos para o formulário de orçamento.
            'veiculo': 'Caminhão', 'modelo': 'Modelo teste', 'ano_veiculo': 2020,
            'tempo_uso': 24, 'quilometragem': 1000, 'peso_toneladas': '2.50',
            'qtd_veiculos': 1, 'tipo_veiculo': '2', 'funcionalidade': '1',
            'manutencao_recente': '1', 'data_ultima_manutencao': '',
            'valor_ultima_manutencao': '100.00',
        }
        dados.update(alteracoes)  # Aplica os valores específicos do cenário.
        return dados

    def criar_orcamento(self, previsao=None):
        veiculo = veiculos.objects.create(  # Cria o veículo associado ao orçamento.
            modelo='Modelo teste', peso=2, tipo='2', funcionalidade='1',
            id_fabricante=self.fabricante, data_fabricacao=date(2020, 1, 1),
            tempo_uso=24, quilometragem=1000,
        )
        return orcamento_ia.objects.create(  # Cria o orçamento que será consultado.
            id_veiculo=veiculo, valor=Decimal('120.00'),
            data_predicao=date(2027, 1, 1), taxa_desvio=Decimal('0.1000'),
            previsao_mensal=previsao or [100, 80, 64, 51.2, 40.96, 32.77],
        )

    def test_home_redireciona_por_cargo_e_rejeita_administrador_sem_cargo_de_area(self):  # Verifica os redirecionamentos e a restrição da página inicial.
        client_estoque = self.cliente_com_cargo('home_estoque', ROLE_STOCK)  # Cria um cliente do setor de estoque.
        client_orcamento = self.cliente_com_cargo('home_orcamento', ROLE_BUDGET)  # Cria um cliente do setor de orçamento.
        client_admin = self.cliente_com_cargo('home_admin', ROLE_ADMIN)  # Cria um administrador sem cargo operacional.

        self.assertRedirects(client_estoque.get(reverse('home')), reverse('lista_pecas'))  # Confirma o redirecionamento do estoque.
        self.assertRedirects(client_orcamento.get(reverse('home')), reverse('orcamento_form'))  # Confirma o redirecionamento do orçamento.
        self.assertRedirects(client_admin.get(reverse('home')), reverse('lista_pecas'))  # Confirma que o administrador pode acessar a área de estoque.

    def test_login_exibe_formulario_autentica_e_rejeita_credenciais_invalidas(self):  # Verifica a exibição e o processamento do login.
        usuario = self.criar_usuario('login_teste', ROLE_STOCK)  # Cria a conta usada na autenticação.
        client = Client()  # Cria o cliente ainda não autenticado.

        self.assertEqual(client.get(reverse('login')).status_code, 200)  # Confirma que a tela de login é exibida.
        resposta_valida = client.post(reverse('login'), {'username': usuario.username, 'password': 'senha123'})  # Envia credenciais válidas.
        self.assertEqual(resposta_valida.status_code, 302)  # Confirma que o login redireciona após autenticar.
        self.assertEqual(resposta_valida.url, reverse('home'))  # Confirma o destino inicial após autenticar.
        resposta_invalida = Client().post(reverse('login'), {'username': usuario.username, 'password': 'incorreta'})  # Envia uma senha incorreta.
        self.assertRedirects(resposta_invalida, reverse('login'))  # Confirma o retorno à tela de login.

    def test_logout_encaminha_para_login(self):  # Verifica o encerramento da sessão do usuário.
        client = self.cliente_com_cargo('logout_teste', ROLE_STOCK)  # Cria um cliente autenticado.

        self.assertRedirects(client.get(reverse('logout')), reverse('login'))  # Confirma o redirecionamento depois do logout.
        self.assertFalse('_auth_user_id' in client.session)  # Confirma que a sessão autenticada foi encerrada.

    def test_registro_exibe_formulario_e_rejeita_nome_existente(self):  # Verifica a exibição do cadastro e a validação de usuário duplicado.
        User.objects.create_user(username='registro_existente', password='senha123')  # Cria previamente o nome de usuário.
        client = Client()  # Cria o cliente não autenticado.

        self.assertEqual(client.get(reverse('registrar')).status_code, 200)  # Confirma que a tela de cadastro é exibida.
        resposta = client.post(reverse('registrar'), {'username': 'registro_existente', 'password': 'senha123'})  # Tenta cadastrar o nome repetido.
        self.assertRedirects(resposta, reverse('registrar'))  # Confirma o retorno ao cadastro.
        self.assertEqual(User.objects.filter(username='registro_existente').count(), 1)  # Confirma que não foi criado outro usuário.

    def test_adicionar_editar_listar_e_excluir_peca(self):  # Verifica os fluxos de criação, consulta, edição e exclusão de peças.
        client = self.cliente_com_cargo('crud_pecas', ROLE_ADMIN)  # Cria um cliente com permissões administrativas.
        dados = {  # Define os campos obrigatórios do formulário de peça.
            'nome': 'Filtro novo', 'categoria': 'Filtros', 'descricao': 'Descrição',
            'fornecedor': self.fornecedor.pk, 'quantidade': 3, 'peso': '1.00',
            'validade': '', 'preco': '15.00', 'id_veiculo': '',
            'id_fabricante': self.fabricante.pk,
        }

        resposta = client.post(reverse('adicionar_peca'), dados)  # Envia o cadastro da peça.
        self.assertRedirects(resposta, reverse('lista_pecas'))  # Confirma o redirecionamento após criar.
        peca = pecas.objects.get(nome='Filtro novo')  # Recupera a peça criada.
        resposta = client.get(reverse('lista_pecas'), {'q': 'Descrição', 'categoria': 'Filtros', 'ordenar': 'preco_desc'})  # Filtra e ordena a listagem.
        self.assertContains(resposta, 'Filtro novo')  # Confirma que a peça filtrada aparece.
        self.assertEqual(resposta.context['ordenar'], 'preco_desc')  # Confirma que a ordenação válida foi mantida.
        self.assertEqual(client.get(reverse('lista_pecas'), {'ordenar': 'desconhecida'}).context['ordenar'], 'nome')  # Confirma a ordenação padrão para opção inválida.
        dados['nome'] = 'Filtro editado'  # Define o novo nome da peça.
        resposta = client.post(reverse('editar_peca', args=[peca.pk]), dados)  # Envia a edição da peça.
        self.assertRedirects(resposta, reverse('lista_pecas'))  # Confirma o redirecionamento após editar.
        self.assertTrue(pecas.objects.filter(pk=peca.pk, nome='Filtro editado').exists())  # Confirma que os dados foram atualizados.
        resposta = client.get(reverse('excluir_peca', args=[peca.pk]))  # Solicita a exclusão da peça.
        self.assertRedirects(resposta, reverse('lista_pecas'))  # Confirma o redirecionamento após excluir.
        self.assertFalse(pecas.objects.filter(pk=peca.pk).exists())  # Confirma que a peça foi removida.

    def test_adicionar_peca_invalida_nao_salva(self):
        client = self.cliente_com_cargo('peca_invalida', ROLE_ADMIN)

        resposta = client.post(
            reverse('adicionar_peca'),
            {'nome': 'Peça incompleta'},
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(resposta.context['form'].errors)
        self.assertFalse(pecas.objects.filter(nome='Peça incompleta').exists())

    def test_editar_peca_invalida_preserva_dados_originais(self):
        peca = self.criar_peca(nome='Peça original')
        client = self.cliente_com_cargo('editar_peca_invalida', ROLE_ADMIN)

        resposta = client.post(
            reverse('editar_peca', args=[peca.pk]),
            {'nome': 'Nome não salvo'},
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(resposta.context['form'].errors)
        peca.refresh_from_db()
        self.assertEqual(peca.nome, 'Peça original')

    def test_funcionario_de_orcamento_nao_acessa_acoes_de_pecas(self):
        peca = self.criar_peca()
        client = self.cliente_com_cargo('orcamento_sem_acesso_pecas', ROLE_BUDGET)
        rotas = (
            ('adicionar_peca', ()),
            ('editar_peca', (peca.pk,)),
            ('excluir_peca', (peca.pk,)),
        )

        for rota, argumentos in rotas:
            with self.subTest(rota=rota):
                resposta = client.get(reverse(rota, args=argumentos))
                self.assertEqual(resposta.status_code, 403)

    def test_lista_pecas_filtra_por_categoria_e_busca_sem_resultados(self):  # Verifica os filtros da listagem de peças.
        self.criar_peca(nome='Filtro de ar')  # Cria uma peça que corresponde à busca.
        client = self.cliente_com_cargo('lista_filtros', ROLE_STOCK)  # Cria um cliente do estoque.

        resposta = client.get(reverse('lista_pecas'), {'q': 'ar', 'categoria': 'Filtros'})  # Pesquisa pelo nome e categoria.
        self.assertContains(resposta, 'Filtro de ar')  # Confirma que a peça correspondente é exibida.
        resposta_vazia = client.get(reverse('lista_pecas'), {'q': 'inexistente'})  # Pesquisa um termo sem correspondência.
        self.assertEqual(list(resposta_vazia.context['pecas_lista']), [])  # Confirma que nenhum resultado é retornado.

    def test_chamados_recebe_formulario_cria_chamado_e_rejeita_dados_invalidos(self):  # Verifica os fluxos de consulta e envio de chamados.
        peca = self.criar_peca()  # Cria a peça associada ao chamado.
        equipamento = equipamentos.objects.create(nome='Equipamento teste', funcao='Teste', id_peca=peca)  # Cria um equipamento disponível.
        client = self.cliente_com_cargo('chamados_teste', ROLE_STOCK)  # Cria um cliente do estoque.

        resposta_form = client.get(reverse('chamados'))  # Abre o formulário de chamados.
        self.assertEqual(resposta_form.status_code, 200)  # Confirma que a tela foi carregada.
        resposta = client.post(reverse('chamados'), {  # Envia um chamado válido.
            'solicitante': 'Solicitante', 'email': 'solicitante@teste.com',
            'telefone': '111111111', 'id_peca': peca.pk,
            'equipamentos': equipamento.pk, 'local': ' Oficina central ',
        })
        self.assertRedirects(resposta, reverse('chamados'))  # Confirma o redirecionamento após criar o chamado.
        chamado = ordem_servico.objects.get()  # Recupera o chamado criado.
        self.assertEqual(chamado.local, 'Oficina central')  # Confirma que o local foi normalizado.
        self.assertEqual(equipamentos.objects.get(pk=equipamento.pk).status, 'em uso')  # Confirma que o equipamento ficou em uso.
        resposta_invalida = client.post(reverse('chamados'), {'solicitante': ''})  # Envia um formulário incompleto.
        self.assertEqual(resposta_invalida.status_code, 200)  # Confirma que o formulário inválido é exibido novamente.

    def test_chamados_exibe_erro_de_validacao_ao_salvar(self):  # Verifica o tratamento de erro de validação no salvamento do chamado.
        peca = self.criar_peca()  # Cria a peça associada ao chamado.
        equipamento = equipamentos.objects.create(nome='Equipamento erro', funcao='Teste', id_peca=peca)  # Cria um equipamento disponível.
        client = self.cliente_com_cargo('chamado_erro', ROLE_STOCK)  # Cria um cliente do estoque.
        dados = {  # Define todos os campos necessários para validar o formulário.
            'solicitante': 'Solicitante', 'email': 'solicitante@teste.com',
            'telefone': '111111111', 'id_peca': peca.pk,
            'equipamentos': equipamento.pk, 'local': 'Oficina central',
        }
        with patch('core.views.ChamadoForm.save', side_effect=ValidationError('erro de teste')):  # Simula o erro de validação tratado pela view.
            resposta = client.post(reverse('chamados'), dados)  # Envia dados válidos para alcançar o salvamento.

        self.assertEqual(resposta.status_code, 200)  # Confirma que o formulário é exibido novamente após a falha de validação.
        self.assertContains(resposta, 'erro de teste')  # Confirma que a mensagem da validação aparece na tela.

    def test_equipamentos_exibe_status_em_uso_quando_existe_chamado_ativo(self):  # Verifica o status apresentado para equipamento com chamado ativo.
        peca = self.criar_peca()  # Cria a peça associada ao equipamento.
        equipamento = equipamentos.objects.create(nome='Equipamento ativo', funcao='Teste', id_peca=peca)  # Cria o equipamento.
        ordem_servico.objects.create(  # Abre um chamado ativo para o equipamento.
            solicitante='Solicitante', email='solicitante@teste.com',
            telefone='111111111', id_peca=peca, equipamentos=equipamento,
        )
        equipamentos.objects.filter(pk=equipamento.pk).update(status='disponivel')  # Simula status desatualizado no banco.
        client = self.cliente_com_cargo('equipamentos_teste', ROLE_STOCK)  # Cria um cliente do estoque.

        resposta = client.get(reverse('equipamentos'))  # Abre a listagem de equipamentos.
        item = resposta.context['equipamentos_lista'][0]  # Obtém o equipamento apresentado na tela.
        self.assertTrue(item.chamado_ativo)  # Confirma que o chamado ativo foi identificado.
        self.assertEqual(item.status_edicao, 'em uso')  # Confirma que o status exibido reflete o chamado.

    def test_alterar_status_equipamento_rejeita_status_invalido_e_chamado_ativo(self):  # Verifica as proteções ao alterar o status do equipamento.
        peca = self.criar_peca()  # Cria a peça do equipamento.
        equipamento = equipamentos.objects.create(nome='Equipamento bloqueado', funcao='Teste', id_peca=peca)  # Cria o equipamento disponível.
        ordem_servico.objects.create(  # Abre um chamado que impede a liberação do equipamento.
            solicitante='Solicitante', email='solicitante@teste.com',
            telefone='111111111', id_peca=peca, equipamentos=equipamento,
        )
        client = self.cliente_com_cargo('status_equipamento', ROLE_ADMIN)  # Cria um cliente administrador.

        resposta_invalida = client.post(reverse('alterar_status_equipamento', args=[equipamento.pk]), {'status': 'invalido'})  # Envia um status inexistente.
        self.assertRedirects(resposta_invalida, reverse('equipamentos'))  # Confirma o retorno à lista de equipamentos.
        resposta_bloqueada = client.post(reverse('alterar_status_equipamento', args=[equipamento.pk]), {'status': 'disponivel'})  # Tenta liberar equipamento com chamado ativo.
        self.assertRedirects(resposta_bloqueada, reverse('equipamentos'))  # Confirma o retorno após bloquear a operação.
        equipamento.refresh_from_db()  # Atualiza o estado do equipamento.
        self.assertEqual(equipamento.status, 'em uso')  # Confirma que o equipamento não foi liberado.

    def test_fornecedores_pedidos_e_relatorios_exibem_dados(self):  # Verifica as páginas de fornecedores, pedidos e relatórios.
        peca = self.criar_peca()  # Cria a peça mostrada nas páginas.
        pedido = pedidos.objects.create(  # Cria um pedido associado à peça.
            id_peca=peca, quantidade=2, preco=peca.preco,
            valor_total=Decimal('25.00'), data_entrega=date(2026, 11, 15),
            id_fornecedor=self.fornecedor, id_fabricante=self.fabricante,
        )
        movimento = estoque.objects.create(  # Cria uma movimentação parcial de estoque.
            quantidade=5, quantidade_saida=2, id_peca=peca, id_fornecedor=self.fornecedor,
        )
        client = self.cliente_com_cargo('listas_relatorios', ROLE_ADMIN)  # Cria um cliente administrador.

        resposta_fornecedores = client.get(reverse('fornecedores'))  # Abre a listagem de fornecedores.
        self.assertEqual(resposta_fornecedores.context['fornecedores_lista'][0], self.fornecedor)  # Confirma que o fornecedor está listado.
        resposta_pedidos = client.get(reverse('pedidos'))  # Abre a listagem de pedidos.
        self.assertEqual(resposta_pedidos.context['pedidos_lista'][0], pedido)  # Confirma que o pedido está listado.
        resposta_relatorios = client.get(reverse('relatorios'))  # Abre os relatórios de estoque e chamados.
        item_movimento = resposta_relatorios.context['movimentacoes'][0]  # Obtém a movimentação apresentada.
        self.assertEqual(item_movimento.quantidade_disponivel, 3)  # Confirma o cálculo da quantidade disponível.
        self.assertEqual(resposta_relatorios.context['orcamentos'], [])  # Confirma a lista vazia de orçamentos.
        self.assertTrue(estoque.objects.filter(pk=movimento.pk).exists())  # Confirma que a consulta não alterou o movimento.

    def test_relatorios_admin_exibe_orcamentos_em_ordem_de_id(self):
        primeiro = self.criar_orcamento()
        segundo = self.criar_orcamento()
        orcamento_ia.objects.filter(pk=primeiro.pk).update(
            data_orcamento=date(2026, 3, 1)
        )
        orcamento_ia.objects.filter(pk=segundo.pk).update(
            data_orcamento=date(2026, 2, 1)
        )
        client_admin = self.cliente_com_cargo('relatorios_admin_orcamentos', ROLE_ADMIN)
        client_estoque = self.cliente_com_cargo('relatorios_estoque_orcamentos', ROLE_STOCK)

        resposta_admin = client_admin.get(reverse('relatorios'))
        resposta_estoque = client_estoque.get(reverse('relatorios'))

        self.assertEqual(
            [orcamento.pk for orcamento in resposta_admin.context['orcamentos']],
            [primeiro.pk, segundo.pk],
        )
        self.assertEqual(resposta_estoque.context['orcamentos'], [])

    def test_entrada_de_estoque_invalida_nao_cria_movimentacao(self):  # Verifica a rejeição de dados inválidos na entrada do estoque.
        client = self.cliente_com_cargo('entrada_invalida', ROLE_ADMIN)  # Cria um cliente administrador.

        resposta = client.post(reverse('registrar_entrada_estoque'), {'quantidade': 0})  # Envia uma quantidade inválida.
        self.assertRedirects(resposta, reverse('relatorios'))  # Confirma o retorno aos relatórios.
        self.assertFalse(estoque.objects.exists())  # Confirma que nenhuma movimentação foi registrada.

    def test_status_de_chamado_invalido_nao_altera_registro(self):  # Verifica a rejeição de status inválido para chamados.
        peca = self.criar_peca()  # Cria a peça associada ao chamado.
        chamado = ordem_servico.objects.create(  # Cria o chamado que terá o status preservado.
            solicitante='Solicitante', email='solicitante@teste.com',
            telefone='111111111', id_peca=peca,
        )
        client = self.cliente_com_cargo('status_chamado_invalido', ROLE_ADMIN)  # Cria um cliente administrador.

        resposta = client.post(reverse('alterar_status_chamado', args=[chamado.pk]), {'status': 'invalido'})  # Envia um status não permitido.
        self.assertRedirects(resposta, reverse('relatorios'))  # Confirma o retorno aos relatórios.
        chamado.refresh_from_db()  # Atualiza o chamado consultado.
        self.assertEqual(chamado.status, 'aberta')  # Confirma que o status original foi mantido.

    def test_saida_de_estoque_rejeita_formulario_e_quantidades_acima_do_disponivel(self):  # Verifica as validações da saída manual de estoque.
        peca = self.criar_peca(quantidade=2)  # Cria uma peça com saldo disponível limitado.
        movimento = estoque.objects.create(  # Cria um movimento com uma unidade ainda disponível.
            quantidade=1, id_peca=peca, id_fornecedor=self.fornecedor,
        )
        client = self.cliente_com_cargo('saida_invalida', ROLE_ADMIN)  # Cria um cliente administrador.

        resposta_formulario = client.post(reverse('registrar_saida_estoque', args=[movimento.pk]), {'quantidade': 0})  # Envia uma quantidade não positiva.
        self.assertRedirects(resposta_formulario, reverse('relatorios'))  # Confirma o retorno aos relatórios.
        resposta_movimento = client.post(reverse('registrar_saida_estoque', args=[movimento.pk]), {'quantidade': 2})  # Excede a quantidade do movimento.
        self.assertRedirects(resposta_movimento, reverse('relatorios'))  # Confirma que o pedido de saída foi recusado.
        movimento.refresh_from_db()  # Atualiza a movimentação do estoque.
        self.assertEqual(movimento.quantidade_saida, 0)  # Confirma que a quantidade de saída não mudou.
        movimento.quantidade = 3  # Amplia o movimento para testar o saldo total da peça.
        movimento.save(update_fields=['quantidade'])  # Salva a alteração usada no cenário.
        resposta_saldo = client.post(reverse('registrar_saida_estoque', args=[movimento.pk]), {'quantidade': 3})  # Excede o saldo atual da peça.
        self.assertRedirects(resposta_saldo, reverse('relatorios'))  # Confirma que a saída acima do saldo foi recusada.
        peca.refresh_from_db()  # Atualiza a peça após as tentativas.
        self.assertEqual(peca.quantidade, 2)  # Confirma que o saldo da peça permaneceu igual.

    def test_formulario_orcamento_rejeita_ausencia_de_fabricante(self):  # Verifica a mensagem quando ainda não existe fabricante cadastrado.
        client = self.cliente_com_cargo('orcamento_sem_fabricante', ROLE_BUDGET)  # Cria um cliente do setor de orçamento.
        self.fabricante.delete()  # Remove o fabricante inicial para simular a ausência desse cadastro.

        resposta = client.post(reverse('orcamento_form'), self.dados_orcamento())  # Envia dados válidos sem fabricante disponível.
        self.assertEqual(resposta.status_code, 200)  # Confirma que o formulário é exibido novamente.
        self.assertContains(resposta, 'Cadastre ao menos um Fabricante')  # Confirma a mensagem de validação apresentada.
        self.assertFalse(orcamento_ia.objects.exists())  # Confirma que nenhum orçamento foi criado.

    def test_formulario_orcamento_calcula_e_salva_previsao(self):  # Verifica a criação de veículo e orçamento com previsão simulada.
        client = self.cliente_com_cargo('orcamento_calculo', ROLE_BUDGET)  # Cria um cliente do setor de orçamento.
        previsao = [100, 80, 64, 51.2, 40.96, 32.77]  # Define os valores mensais retornados pelo modelo.
        with patch('core.views._prever_orcamento', return_value=(previsao, Decimal('368.93'), Decimal('0.1000'))):  # Isola a previsão de IA.
            resposta = client.post(reverse('orcamento_form'), self.dados_orcamento())  # Envia os dados para gerar o orçamento.

        orcamento = orcamento_ia.objects.get()  # Recupera o orçamento persistido.
        self.assertRedirects(resposta, reverse('orcamento_grafico', args=[orcamento.pk]))  # Confirma o redirecionamento ao gráfico.
        self.assertEqual(orcamento.previsao_mensal, previsao)  # Confirma que a previsão foi armazenada.
        self.assertEqual(orcamento.valor, Decimal('368.93'))  # Confirma o valor total calculado.
        self.assertEqual(orcamento.status, 'pendente')  # Confirma o status inicial do orçamento.

    def test_formulario_orcamento_deriva_quantidade_e_valor_da_peca(self):
        peca = self.criar_peca(quantidade=5)
        client = self.cliente_com_cargo('orcamento_com_peca', ROLE_BUDGET)
        dados = self.dados_orcamento(peca=peca.pk, quantidade_utilizada='3')
        previsao = [100, 80, 64, 51.2, 40.96, 32.77]

        with patch(
            'core.views._prever_orcamento',
            return_value=(previsao, Decimal('368.93'), Decimal('0.1000')),
        ) as prever:
            resposta = client.post(reverse('orcamento_form'), dados)

        self.assertEqual(resposta.status_code, 302)
        caso = prever.call_args.args[0]
        self.assertEqual(caso['qtd_pecas'], 3)
        self.assertEqual(caso['valor_pecas'], 37.5)

    def test_formulario_orcamento_rejeita_quantidade_de_pecas_acima_do_estoque(self):
        peca = self.criar_peca(quantidade=2)
        client = self.cliente_com_cargo('orcamento_sem_estoque', ROLE_BUDGET)

        resposta = client.post(
            reverse('orcamento_form'),
            self.dados_orcamento(peca=peca.pk, quantidade_utilizada='3'),
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'Quantidade indisponível em estoque (2 un. disponíveis).')
        self.assertFalse(orcamento_ia.objects.exists())

    def test_formulario_orcamento_invalido_reexibe_formulario(self):  # Verifica a reexibição do formulário de orçamento inválido.
        client = self.cliente_com_cargo('orcamento_invalido', ROLE_BUDGET)  # Cria um cliente do setor de orçamento.

        resposta_get = client.get(reverse('orcamento_form'))  # Abre o formulário de orçamento.
        self.assertIsInstance(resposta_get.context['form'], OrcamentoIAForm)  # Confirma o formulário apresentado.
        resposta_post = client.post(reverse('orcamento_form'), {'modelo': ''})  # Envia dados incompletos.
        self.assertEqual(resposta_post.status_code, 200)  # Confirma que a página é exibida novamente.
        self.assertFalse(orcamento_ia.objects.exists())  # Confirma que nenhum orçamento foi salvo.

    def test_grafico_exibe_orcamento_especifico_e_mais_recente(self):  # Verifica a seleção de orçamento na view do gráfico.
        antigo = self.criar_orcamento([10, 8])  # Cria um orçamento para consultar diretamente.
        recente = self.criar_orcamento([20, 16])  # Cria outro orçamento para a consulta padrão.
        orcamento_ia.objects.filter(pk=antigo.pk).update(data_orcamento=date(2026, 1, 1))  # Define a data do primeiro orçamento.
        orcamento_ia.objects.filter(pk=recente.pk).update(data_orcamento=date(2026, 2, 1))  # Define a data do orçamento mais recente.
        client = self.cliente_com_cargo('grafico_orcamento', ROLE_BUDGET)  # Cria um cliente do setor de orçamento.

        resposta_especifica = client.get(reverse('orcamento_grafico', args=[antigo.pk]))  # Abre o gráfico de um orçamento específico.
        self.assertEqual(resposta_especifica.context['orcamento'], antigo)  # Confirma que o orçamento solicitado foi escolhido.
        self.assertEqual(resposta_especifica.context['previsao'], [10, 8])  # Confirma a projeção exibida.
        resposta_recente = client.get(reverse('orcamento_grafico'))  # Abre o gráfico sem informar um identificador.
        self.assertEqual(resposta_recente.context['orcamento'], recente)  # Confirma a seleção do orçamento mais recente.

    def test_historico_de_orcamentos_monta_rotulos_e_valores(self):  # Verifica os dados preparados para o histórico de orçamentos.
        orcamento = self.criar_orcamento()  # Cria o orçamento exibido no histórico.
        client = self.cliente_com_cargo('historico_orcamento', ROLE_BUDGET)  # Cria um cliente do setor de orçamento.

        resposta = client.get(reverse('orcamentos_historico'))  # Abre o histórico de orçamentos.
        self.assertEqual(resposta.context['orcamentos'], [orcamento])  # Confirma que o orçamento foi listado.
        self.assertIn('Modelo teste', resposta.context['rotulos'][0])  # Confirma que o rótulo identifica o veículo.
        self.assertEqual(resposta.context['valores'], [120.0])  # Confirma os valores preparados para o gráfico.

    def test_pdf_de_orcamento_responde_com_arquivo_pdf(self):  # Verifica o download do PDF de um orçamento.
        orcamento = self.criar_orcamento()  # Cria o orçamento que será convertido em PDF.
        client = self.cliente_com_cargo('pdf_orcamento', ROLE_BUDGET)  # Cria um cliente do setor de orçamento.

        resposta = client.get(reverse('orcamento_pdf', args=[orcamento.pk]))  # Solicita o PDF do orçamento.
        self.assertEqual(resposta.status_code, 200)  # Confirma que a geração foi concluída.
        self.assertEqual(resposta['Content-Type'], 'application/pdf')  # Confirma o tipo do conteúdo retornado.
        self.assertIn(f'orcamento_{orcamento.pk}.pdf', resposta['Content-Disposition'])  # Confirma o nome do arquivo baixado.
        self.assertTrue(resposta.content.startswith(b'%PDF'))  # Confirma que o conteúdo possui assinatura de PDF.

    def test_helpers_de_rotulos_e_campos_da_previsao(self):  # Verifica a montagem de meses e dados para a IA preditiva.
        from core.views import _campo_predicao, _rotulos_meses  # Importa os helpers privados exercitados diretamente.
        dados = {  # Define os valores de entrada do helper de previsão.
            'qtd_veiculos': 2, 'qtd_pecas': 3, 'ano_veiculo': 2020,
            'peso_toneladas': Decimal('1.50'), 'tipo_veiculo': '2',
            'funcionalidade': '1', 'quilometragem': 100, 'tempo_uso': 12,
            'manutencao_recente': '1', 'data_ultima_manutencao': date(2026, 1, 1),
            'valor_ultima_manutencao': Decimal('50'), 'valor_pecas': Decimal('25'),
        }

        self.assertEqual(_rotulos_meses(4, date(2026, 11, 1)), ['Nov', 'Dez', 'Jan', 'Fev'])  # Confirma a virada do ano nos rótulos.
        caso = _campo_predicao(dados)  # Converte os valores ao formato esperado pelo modelo.
        self.assertEqual(caso['ano_fabricacao'], 2020)  # Confirma o nome esperado para o ano.
        self.assertEqual(caso['data_ultima_manutencao'], 1)  # Confirma que a data vira indicador binário.
        self.assertEqual(caso['peso_toneladas'], 1.5)  # Confirma a conversão do peso para número decimal.

    def test_previsao_treina_modelo_e_nao_retorna_valor_negativo(self):  # Verifica treinamento sob demanda, arredondamento e piso da previsão.
        from core.views import _prever_orcamento  # Importa o helper privado de previsão.
        with patch('orcamentos.ia_preditiva.MODEL_PATH') as caminho_modelo:  # Simula a ausência inicial do modelo treinado.
            caminho_modelo.exists.return_value = False  # Indica que ainda não há modelo salvo.
            with patch('orcamentos.ia_preditiva.treinar') as treinar:  # Substitui o treinamento real do modelo.
                with patch('orcamentos.ia_preditiva.prever', return_value=-10.125):  # Simula uma previsão negativa.
                    with patch('orcamentos.ia_preditiva.carregar_taxa_desvio', return_value=0.123456):  # Simula a taxa de desvio.
                        previsao, total, desvio = _prever_orcamento({'entrada': 1})  # Executa a previsão controlada.

        treinar.assert_called_once_with()  # Confirma que o modelo foi treinado quando não existia.
        self.assertEqual(previsao, [0.0] * 6)  # Confirma que os valores negativos foram limitados a zero.
        self.assertEqual(total, Decimal('0.00'))  # Confirma o total calculado da previsão.
        self.assertEqual(desvio, Decimal('0.1235'))  # Confirma o arredondamento da taxa de desvio.

    def test_previsao_reutiliza_modelo_existente_sem_treinar(self):
        from core.views import _prever_orcamento

        with patch('orcamentos.ia_preditiva.MODEL_PATH') as caminho_modelo:
            caminho_modelo.exists.return_value = True
            with patch('orcamentos.ia_preditiva.treinar') as treinar:
                with patch('orcamentos.ia_preditiva.prever', return_value=10.126):
                    with patch(
                        'orcamentos.ia_preditiva.carregar_taxa_desvio',
                        return_value=0.123456,
                    ):
                        previsao, total, desvio = _prever_orcamento({'entrada': 1})

        treinar.assert_not_called()
        self.assertEqual(previsao[0], 10.13)
        self.assertEqual(total, Decimal('37.37'))
        self.assertEqual(desvio, Decimal('0.1235'))


class ResultadosTestesViewTest(TestCase):  # Verifica acesso à página administrativa de resultados dos testes.
    def test_administrador_visualiza_pagina_de_resultados(self):  # Confirma que a página de resultados está disponível para administradores.
        usuario = User.objects.create_user(username='admin_resultados', password='senha123')  # Cria a conta administrativa.
        usuario.groups.add(Group.objects.get(name=ROLE_ADMIN))  # Associa o usuário ao grupo de administradores.
        client = Client()  # Cria o cliente para simular a navegação.
        client.force_login(usuario)  # Autentica o administrador.

        resposta = client.get(reverse('resultados_testes'))  # Abre a página dos resultados.
        self.assertEqual(resposta.status_code, 200)  # Confirma que a página foi carregada.
        self.assertContains(resposta, 'Resultados dos testes')  # Confirma o título exibido.

    def test_pagina_exibe_casos_do_relatorio_salvo(self):  # Confirma que a página carrega os resultados gravados pelo runner.
        usuario = User.objects.create_user(username='admin_resultados_salvos', password='senha123')  # Cria a conta administrativa.
        usuario.groups.add(Group.objects.get(name=ROLE_ADMIN))  # Associa o usuário ao grupo de administradores.
        client = Client()  # Cria o cliente para simular a navegação.
        client.force_login(usuario)  # Autentica o administrador.
        relatorio = {  # Monta um relatório com um caso para exibir na página.
            'executado_em': '2026-10-22T12:00:00+00:00', 'total': 1,
            'totais': {'passou': 1, 'falhou': 0, 'erro': 0, 'ignorado': 0},
            'status': 'aprovado',
            'casos': [{'nome': 'test_caso_exemplo', 'status': 'passou'}],
        }
        with tempfile.TemporaryDirectory() as diretorio:  # Cria uma pasta temporária para o relatório da view.
            pasta_relatorio = Path(diretorio) / '.test-results'  # Define a pasta lida pela view.
            pasta_relatorio.mkdir()  # Cria a pasta temporária do relatório.
            (pasta_relatorio / 'latest.json').write_text(json.dumps(relatorio), encoding='utf-8')  # Salva o relatório de exemplo.
            with override_settings(BASE_DIR=Path(diretorio)):  # Aponta a view para a pasta temporária.
                resposta = client.get(reverse('resultados_testes'))  # Abre a página com um relatório disponível.

        self.assertContains(resposta, 'test_caso_exemplo')  # Confirma que o caso salvo aparece na página.
        self.assertContains(resposta, 'Aprovado')  # Confirma que o status geral aparece na página.

    def test_funcionario_de_estoque_nao_acessa_pagina_de_resultados(self):  # Confirma que a página não fica disponível ao estoque.
        usuario = User.objects.create_user(username='estoque_resultados', password='senha123')  # Cria a conta do funcionário.
        usuario.groups.add(Group.objects.get(name=ROLE_STOCK))  # Associa o usuário ao grupo de estoque.
        client = Client()  # Cria o cliente para simular a navegação.
        client.force_login(usuario)  # Autentica o funcionário.

        resposta = client.get(reverse('resultados_testes'))  # Tenta abrir a página administrativa.
        self.assertEqual(resposta.status_code, 403)  # Confirma que o acesso foi negado.

    def test_runner_persiste_resultado_para_a_pagina(self):  # Confirma que o runner salva o relatório consultado pela página.
        from core.test_runner import TestReportRunner  # Importa o runner que registra os resultados.
        caso = {'nome': 'test_exemplo', 'status': 'passou'}  # Define um caso concluído com sucesso.
        resultado = SimpleNamespace(  # Monta um resultado mínimo compatível com o runner.
            cases=[caso], testsRun=1, wasSuccessful=lambda: True,
        )
        with tempfile.TemporaryDirectory() as diretorio:  # Cria uma pasta temporária para o relatório.
            with override_settings(BASE_DIR=Path(diretorio)):  # Direciona a gravação para a pasta temporária.
                TestReportRunner._salvar_relatorio(resultado)  # Salva o relatório de teste.
            caminho = Path(diretorio) / '.test-results' / 'latest.json'  # Localiza o arquivo criado pelo runner.
            relatorio = json.loads(caminho.read_text(encoding='utf-8'))  # Lê o JSON consumido pela página.

        self.assertEqual(relatorio['status'], 'aprovado')  # Confirma o status geral persistido.
        self.assertEqual(relatorio['totais']['passou'], 1)  # Confirma a contagem de testes aprovados.
        self.assertEqual(relatorio['casos'], [caso])  # Confirma que os detalhes do caso foram persistidos.
