import core.storage
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0006_estoque_quantidade_saida'),
    ]

    operations = [
        migrations.AddField(
            model_name='pedidos',
            name='data_criacao',
            field=models.DateTimeField(
                auto_now_add=True,
                default=django.utils.timezone.now,
            ),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='pecas',
            name='imagem',
            field=models.ImageField(
                blank=True,
                null=True,
                storage=core.storage.DeduplicatingImageStorage(),
                upload_to='pecas/',
            ),
        ),
    ]
