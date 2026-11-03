from django.shortcuts import render  # Renderiza a página de erro padronizada.
from django.template import TemplateDoesNotExist, TemplateSyntaxError  # Identifica falhas de carregamento de templates.
from django.utils.deprecation import MiddlewareMixin  # Fornece a interface tradicional de middleware.


class ErrorPageMiddleware(MiddlewareMixin):  # Converte erros selecionados em respostas HTML amigáveis.
    @staticmethod  # Não depende de estado da instância do middleware.
    def _render_error(request, status, title, message):  # Centraliza a renderização da página de erro.
        return render(  # Retorna a página com os dados do erro.
            request,  # Encaminha a requisição para o contexto do template.
            'core/acesso_negado.html',  # Usa a tela padrão de acesso e erro.
            {  # Prepara os campos consumidos pelo template.
                'error_code': status,  # Informa o código HTTP exibido.
                'error_title': title,  # Define o título da mensagem.
                'error_message': message,  # Define a explicação apresentada ao usuário.
            },
            status=status,  # Mantém o status HTTP correspondente ao erro.
        )

    def process_response(self, request, response):  # Ajusta respostas HTTP de páginas inexistentes.
        if response.status_code == 404:  # Substitui apenas respostas de não encontrado.
            return self._render_error(  # Renderiza a mensagem 404 da aplicação.
                request,  # Mantém a requisição original.
                404,  # Preserva o código de página inexistente.
                'Página não encontrada',  # Define o título do erro.
                'A página que você procura não existe ou foi movida.',  # Explica a causa ao usuário.
            )
        return response  # Deixa as demais respostas inalteradas.

    def process_exception(self, request, exception):  # Trata exceções específicas durante a renderização.
        if isinstance(exception, (TemplateDoesNotExist, TemplateSyntaxError)):  # Filtra falhas relacionadas a templates.
            return self._render_error(  # Retorna uma página de erro interno controlada.
                request,  # Mantém a requisição original.
                500,  # Informa falha interna do servidor.
                'Erro ao carregar a página',  # Define o título apresentado.
                'Ocorreu um erro ao carregar esta página. Tente novamente mais tarde.',  # Evita expor detalhes técnicos.
            )
        return None  # Deixa outras exceções para o tratamento padrão do Django.
