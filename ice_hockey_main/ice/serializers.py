from rest_framework import serializers
from .models import Transmitter, Read
from django.utils import timezone

class ReadSerializer(serializers.ModelSerializer):
    distance = serializers.IntegerField(write_only=True, required=False)

    class Meta:
        model = Read
        fields = ['timeStampUTC','timeStampUTC', 'deviceUID', 'manufacturerName', 'distance', 'distance1', 'distance2', 'distance3', 'count']
        extra_kwargs = {
            'count': {'required': False},
            'distance1': {'required': False},
            'distance2': {'required': False},
            'distance3': {'required': False},
        }

class TransmitterSerializer(serializers.ModelSerializer):
    reads = ReadSerializer(many=True)

    class Meta:
        model = Transmitter
        fields = ['transmitterSerialNumber', 'nodeType', 'nodeSerialNumber', 'reads', 'allCount']

    def create(self, validated_data):
        reads_data = validated_data.pop('reads')
        transmitter = Transmitter.objects.create(**validated_data)
        for read_data in reads_data:
            device_uid = read_data.pop('deviceUID')
            distance = read_data.pop('distance', None)
            if distance is not None:
                if transmitter.transmitterSerialNumber == '1000CB':
                    read_data['distance1'] = distance
                elif transmitter.transmitterSerialNumber == '1000ED':
                    read_data['distance2'] = distance
                elif transmitter.transmitterSerialNumber == '10012B':
                    read_data['distance3'] = distance
            Read.objects.create(transmitter=transmitter, deviceUID=device_uid, **read_data)
        return transmitter
    def update(self, instance, validated_data):
        reads_data = validated_data.pop('reads', None)

        if reads_data:
            for read_data in reads_data:
                device_uid = read_data.pop('deviceUID')
                distance = read_data.pop('distance', None)

                existing_read = instance.reads.filter(deviceUID=device_uid).first()

                if existing_read:
                    if distance is not None:
                        if instance.transmitterSerialNumber == '1000CB':
                            existing_read.distance1 = distance
                        elif instance.transmitterSerialNumber == '1000ED':
                            existing_read.distance2 = distance
                        elif instance.transmitterSerialNumber == '10012B':
                            existing_read.distance3 = distance

                    for key, value in read_data.items():
                        setattr(existing_read, key, value)

                    # Update timeStampUTC for this specific deviceUID
                    existing_read.timeStampUTC = timezone.now()
                    existing_read.save()

                else:
                    if distance is not None:
                        if instance.transmitterSerialNumber == '1000CB':
                            read_data['distance1'] = distance
                        elif instance.transmitterSerialNumber == '1000ED':
                            read_data['distance2'] = distance
                        elif instance.transmitterSerialNumber == '10012B':
                            read_data['distance3'] = distance
                    # Set timeStampUTC for new read_data
                    read_data['timeStampUTC'] = timezone.now()

                    Read.objects.create(transmitter=instance, deviceUID=device_uid, **read_data)

        instance.transmitterSerialNumber = validated_data.get('transmitterSerialNumber',
                                                              instance.transmitterSerialNumber)
        instance.nodeType = validated_data.get('nodeType', instance.nodeType)
        instance.nodeSerialNumber = validated_data.get('nodeSerialNumber', instance.nodeSerialNumber)
        instance.allCount = validated_data.get('allCount', instance.allCount)

        instance.save()
        return instance

    