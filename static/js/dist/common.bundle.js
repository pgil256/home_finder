/*
 * ATTENTION: The "eval" devtool has been used (maybe by default in mode: "development").
 * This devtool is neither made for production nor for readable output files.
 * It uses "eval()" calls to create a separate source file in the browser devtools.
 * If you are trying to read the output file, select a different devtool (https://webpack.js.org/configuration/devtool/)
 * or disable the default devtool with "devtool: false".
 * If you are looking for production-ready output files, see mode: "production" (https://webpack.js.org/configuration/mode/).
 */
/******/ (() => { // webpackBootstrap
/******/ 	var __webpack_modules__ = ({

/***/ "./static/js/dev/common.js":
/*!*********************************!*\
  !*** ./static/js/dev/common.js ***!
  \*********************************/
/***/ (() => {

eval("$(document).ready(function () {\n  $('#learnMoreButton').on('click', function (event) {\n    event.preventDefault();\n    var $sectionToScrollTo = $('#learn-more');\n    if ($sectionToScrollTo.length) {\n      $('html, body').animate({\n        scrollTop: $sectionToScrollTo.offset().top\n      }, 1500); // Duration of the scroll in milliseconds\n    } else {\n      console.error('Section to scroll to not found.');\n    }\n  });\n});\n\n//# sourceURL=webpack://home_finder/./static/js/dev/common.js?");

/***/ })

/******/ 	});
/************************************************************************/
/******/ 	
/******/ 	// startup
/******/ 	// Load entry module and return exports
/******/ 	// This entry module can't be inlined because the eval devtool is used.
/******/ 	var __webpack_exports__ = {};
/******/ 	__webpack_modules__["./static/js/dev/common.js"]();
/******/ 	
/******/ })()
;