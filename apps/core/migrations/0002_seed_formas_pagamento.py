from django.db import migrations

FORMAS_PAGAMENTO = [
    ('Dinheiro', '0'),
    ('Pix', '0'),
    ('Débito', '1.50'),
    ('Crédito', '3.50'),
    ('iFood', '12.00'),
]


def seed(apps, schema_editor):
    FormaPagamento = apps.get_model('core', 'FormaPagamento')
    for nome, taxa in FORMAS_PAGAMENTO:
        FormaPagamento.objects.get_or_create(nome=nome, defaults={'taxa_percentual': taxa})


def unseed(apps, schema_editor):
    FormaPagamento = apps.get_model('core', 'FormaPagamento')
    FormaPagamento.objects.filter(nome__in=[nome for nome, _ in FORMAS_PAGAMENTO]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
