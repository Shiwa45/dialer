import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'autodialer.settings')
django.setup()

from telephony.models import Phone, PsEndpoint, PsAuth, PsAor

def main():
    phones = Phone.objects.all()
    print(f"Phones: {phones.count()}")
    for p in phones[:10]:
        print(f" - {p.extension} user={getattr(p.user, 'username', None)} server={p.asterisk_server.name}")

    endpoints = PsEndpoint.objects.count()
    auths = PsAuth.objects.count()
    aors = PsAor.objects.count()
    print(f"ps_endpoints={endpoints} ps_auths={auths} ps_aors={aors}")

    missing = []
    for p in phones:
        if not PsEndpoint.objects.filter(id=p.extension).exists():
            missing.append(p.extension)
    if missing:
        print("Missing in ps_endpoints:", ", ".join(missing))
    else:
        print("All phones present in ps_endpoints")

if __name__ == '__main__':
    main()

