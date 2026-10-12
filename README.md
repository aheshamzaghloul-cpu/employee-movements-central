# Employee Movements — Review v68.15.43

نسخة مراجعة لمعالجة البحث الشامل عن المأموريات وفلاتر الفروع. لا ترفع هذه النسخة تلقائيًا إلى GitHub أو Blitz ولا تجري أي تغييرات على قاعدة البيانات.

تتضمن هذه النسخة إزالة شرط اختيار محافظة العمل من صفحة المأموريات، وإتاحة فلاتر الفروع على مستوى جميع المحافظات النشطة، وإظهار المحافظة بجانب اسم الفرع لتقليل الالتباس عند تكرار أسماء الفروع.

يرجى اختبار تسجيل الدخول بالأدوار المختلفة، فتح صفحة المأموريات دون اختيار محافظة عمل، البحث عن مأمورية في محافظة أخرى، وفتح/طباعة PDF، ثم التأكد من أن التعديل والإغلاق ما زالا يخضعان للصلاحيات الأصلية.


### Employee Excel branch matching (v68.22.33)
Employee imports now prefer the registered active branch code. A unique code resolves the canonical branch and governorate even when workbook labels differ. Duplicate codes are disambiguated by governorate/name when possible and otherwise rejected rather than guessed. Files without branch codes retain normalized governorate + branch-name matching.
