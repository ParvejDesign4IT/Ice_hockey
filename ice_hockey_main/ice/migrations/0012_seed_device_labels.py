from django.db import migrations


INITIAL_MAPPING = {
    "200080": "1",
    "200081": "2",
    "200082": "3",
    "200086": "4",
    "200088": "5",
   
     
}


def seed_labels(apps, schema_editor):
    DeviceLabel = apps.get_model('ice', 'DeviceLabel')
    for uid, label in INITIAL_MAPPING.items():
        DeviceLabel.objects.update_or_create(
            deviceUID=uid,
            defaults={"label": label},
        )


def unseed_labels(apps, schema_editor):
    DeviceLabel = apps.get_model('ice', 'DeviceLabel')
    DeviceLabel.objects.filter(deviceUID__in=INITIAL_MAPPING.keys()).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('ice', '0011_devicelabel'),
    ]

    operations = [
        migrations.RunPython(seed_labels, unseed_labels),
    ]