from django.db import migrations


INITIAL_MAPPING = {
    "200080": "1",
    "200081": "2",
    "200082": "3",
    "200083": "4",
    "200084": "5",
    "200085": "6",
    "200086": "7",
    "200087": "8",
    "200088": "9",
    "200089": "10",
     
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