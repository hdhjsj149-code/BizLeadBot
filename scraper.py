import os
import csv
import requests
from datetime import datetime
from config import SEARCH_QUERY, OUTPUT_DIR

def scrape_leads():
    """
    مُستخرج البيانات (Scraper) المحدث لـ BizLeadBot
    يقوم بجلب بيانات العملاء المحتملين وتخزينها بصيغة منظمة
    """
    print(f"[*] بدء عملية البحث والسحب عن: {SEARCH_QUERY}")
    
    # محاكاة أو جلب البيانات الحقيقية (يمكن ربطه بـ Google Places API أو BeautifulSoup)
    # هنا نموذج هيكلي متطور لتنظيم النتائج وتصديرها مباشرة
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

    # التأكد من وجود مجلد المخرجات
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = os.path.join(OUTPUT_DIR, f"leads_{timestamp}.csv")

    # حفظ البيانات في ملف CSV
    keys = leads_data[0].keys() if leads_data else []
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        dict_writer = csv.DictWriter(f, fieldnames=keys)
        dict_writer.writeheader()
        dict_writer.writerows(leads_data)

    print(f"[+] تم الحفظ بنجاح في المسار: {output_file}")
    return output_file

if __name__ == "__main__":
    scrape_leads()
