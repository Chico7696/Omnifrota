from django.apps import AppConfig  # Classe-base para configurar aplicativos Django.
    

class CoreConfig(AppConfig):  # Declara a configuração do aplicativo core.
    name = 'core'  # Define o rótulo Python do aplicativo.

    def ready(self):  # Conecta inicializações executadas depois das migrações.
        from django.db.models.signals import post_migrate  # Importa o sinal pós-migração.
        from .access_control import configurar_grupos_de_cargos  # Importa a rotina de sincronização de cargos.

        post_migrate.connect(  # Associa a sincronização ao ciclo de migração do app.
            configurar_grupos_de_cargos,  # Callback de criação e atualização dos grupos.
            sender=self,  # Limita o sinal às migrações de core.
            dispatch_uid='core.configurar_grupos_de_cargos',  # Evita conexões duplicadas do callback.
        )
