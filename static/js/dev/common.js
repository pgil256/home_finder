$(document).ready(function() {
    $('#learnMoreButton').on('click', function(event) {
        event.preventDefault();
        var $sectionToScrollTo = $('#learn-more');
        if ($sectionToScrollTo.length) {
            $('html, body').animate({
                scrollTop: $sectionToScrollTo.offset().top
            }, 1500);  // Duration of the scroll in milliseconds
        } else {
            console.error('Section to scroll to not found.');
        }
    });
});
