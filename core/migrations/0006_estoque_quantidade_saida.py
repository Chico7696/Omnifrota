from django.db import migrations, models
from django.db.models import F


def preencher_saidas_existentes(apps, schema_editor):
    estoque = apps.get_model('core', 'estoque')
    estoque.objects.using(schema_editor.connection.alias).filter(
        data_saida__isnull=False
    ).update(quantidade_saida=F('quantidade'))


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0005_reset_orcamento_ids'),
    ]

    operations = [
        migrations.AddField(
            model_name='estoque',
            name='quantidade_saida',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.RunPython(preencher_saidas_existentes, migrations.RunPython.noop),
    ]
