import os
import csv
from datetime import datetime
from config import OUTPUT_DIR, REQUEST_TIMEOUT

# تعريف متغير البحث الافتراضي
SEARCH_QUERY = "Digital Marketing"

class ScraperError(Exception):
    """مخصص لأخطاء عملية السحب"""
    pass

def scrape_leads():
    """
    مُستخرج البيانات الرئيسي لـ BizLeadBot مع الاعتماد على إعدادات المشروع
    """
    print(f"[*] بدء عملية البحث والسحب بمهلة طلبات: {REQUEST_TIMEOUT} ثانية")
    
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
    تصدير النتائج إلى ملف CSV بالاعتماد على مسار المخرجات من config
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