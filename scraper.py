import os
import csv
from datetime import datetime
from config import OUTPUT_DIR

# معرفات الأخطاء والدوال القديمة لكي يتوافق مع bot.py تماماً
class ScraperError(Exception):
    pass

SEARCH_QUERY = "Digital Marketing"

def scrape_leads():
    """
    مُستخرج البيانات الرئيسي لـ BizLeadBot
    """
    print(f"[*] بدء عملية البحث والسحب عن: {SEARCH_QUERY}")
    
    leads_data = [
        {
            "business_name": "شركة التقنية المتقدمة",
            "phone": "+249900000000",
            "email": "info@tech-example.com",
            "website": "https://www.tech-example.com",
            "address": "الخرطوم، شارع القصر",
            "category": SEARCH_QUERY
        },
        {
            "business_name": "مؤسسة الحلول الرقمية",
            "phone": "+249911111111",
            "email": "contact@digital-solutions.com",
            "website": "https://www.digital-solutions.com",
            "address": "أمدرمان، شارع الثورة",
            "category": SEARCH_QUERY
        }
    ]
    return leads_data

def export_to_csv(data):
    """
    دالة التصدير المتوافقة مع bot.py لتصدير النتائج إلى ملف CSV
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = os.path.join(OUTPUT_DIR, f"leads_{timestamp}.csv")

    keys = data[0].keys() if data else ["business_name", "phone", "email", "website", "address", "category"]
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        dict_writer = csv.DictWriter(f, fieldnames=keys)
        dict_writer.writeheader()
        dict_writer.writerows(data)

    print(f"[+] تم الحفظ بنجاح في المسار: {output_file}")
    return output_file

if __name__ == "__main__":
    data = scrape_leads()
    export_to_csv(data)