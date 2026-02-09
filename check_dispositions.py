from campaigns.models import Disposition

print(f"{'Name':<30} | {'Code':<20} | {'Category':<20}")
print("-" * 80)

for d in Disposition.objects.all():
    print(f"{d.name:<30} | {d.code:<20} | {d.category:<20}")
