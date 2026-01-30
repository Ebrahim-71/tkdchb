(function() {
    // همیشه jQuery ادمین رو بگیر
    var $ = (window.django && django.jQuery) ? django.jQuery : window.jQuery;

    if (!$) {
        console.error("PersianDatepicker: jQuery not found!");
        return;
    }

    function initPersianDatepicker(context) {
        // context برای این‌لاین‌هاست؛ اگر ندادیم، کل داکیومنت
        context = context || document;

        // فیلدهایی که کلاس pdate دارن (همینی که تو HTML دیدی)
        var $inputs = $('input.pdate', context);

        console.log("PersianDatepicker: found", $inputs.length, "inputs");

        $inputs.each(function() {
            var $input = $(this);

            // اگر قبلاً وصل شده، دوباره وصل نکن
            if ($input.data("hasPersianDatepicker")) {
                return;
            }
            $input.data("hasPersianDatepicker", true);

            $input.persianDatepicker({
                initialValueType: "gregorian",
                format: "YYYY/MM/DD",
                calendarType: "persian",
                autoClose: true,
                calendar: {
                    persian: {
                        locale: "fa",
                        leapYearMode: "algorithmic"
                    }
                },
                toolbox: {
                    calendarSwitch: {
                        enabled: false
                    },
                    todayButton: {
                        enabled: true,
                        text: {
                            fa: "امروز"
                        }
                    }
                },
                navigator: {
                    scroll: {
                        enabled: false
                    }
                }
            });
        });
    }

    // وقتی ادمین لود شد
    $(function() {
        initPersianDatepicker(document);
    });

    // برای فرم‌های این‌لاین (اگر داشتی)
    $(document).on("formset:added", function(event, $row, formsetName) {
        initPersianDatepicker($row.get(0));
    });
})();
