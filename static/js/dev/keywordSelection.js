import Sortable from "sortablejs";

document.addEventListener("DOMContentLoaded", () => {
    setupKeywordLoading();
    setupSubmitAction();
});

function setupKeywordLoading() {
    const availableKeywords = document.getElementById("available-keywords");
    const sortableList = document.getElementById("sortable-container");
    const numberingList = document.getElementById("numbering-list");

    fetchKeywords(availableKeywords, sortableList, numberingList);
}

function fetchKeywords(availableKeywords, sortableList, numberingList) {
    fetch("get-keywords/")
    .then(response => response.json())
    .then(data => {
        populateKeywords(data.keywords, availableKeywords, sortableList, numberingList);
    });
}

function populateKeywords(keywords, availableKeywords, sortableList, numberingList) {
    keywords.forEach(keyword => {
        let item = createKeywordElement(keyword);
        item.onclick = () => moveKeywordToSortable(item, sortableList, numberingList);
        availableKeywords.appendChild(item);
    });
}

function createKeywordElement(keyword) {
    const item = document.createElement("div");
    item.className = "keyword flex items-center h-10 m-3 pl-3 pr-3 bg-white border border-gray-200 rounded cursor-pointer shadow transition duration-400 ease-in-out hover:border-orange-300 hover:shadow-md";

    // Create plus button
    const addButton = document.createElement("img");
    addButton.src = "https://icons.getbootstrap.com/assets/icons/plus.svg";
    addButton.alt = "Add";
    addButton.className = "w-4 h-4 mr-2 cursor-pointer";
    item.appendChild(addButton);

    // Add keyword text
    const keywordText = document.createElement("div");
    keywordText.textContent = keyword;
    keywordText.className = "flex-grow text-center text-sm text-gray-800";
    item.appendChild(keywordText);

    return item;
}

function moveKeywordToSortable(keyword, sortableList, numberingList) {
    const listItem = createSortableListItem(keyword);
    sortableList.appendChild(listItem);
    keyword.remove();
    updateNumbering(numberingList, sortableList);
    ensureSortable(sortableList);
}

function createSortableListItem(keyword) {
    const listItem = document.createElement("li");
    listItem.className = "sortable-item flex items-center justify-between h-10 pl-4 mr-2 bg-white border border-gray-200 rounded mb-2 cursor-pointer shadow transition duration-400 ease-in-out hover:border-orange-300 hover:shadow-md";

    const textSpan = document.createElement("span");
    textSpan.textContent = keyword.textContent;
    textSpan.className = "block text-sm text-gray-800";
    listItem.appendChild(textSpan);

    const deleteButton = document.createElement("img");
    deleteButton.src = "https://icons.getbootstrap.com/assets/icons/trash.svg";
    deleteButton.alt = "Delete";
    deleteButton.className = "w-4 h-4 mr-2 cursor-pointer";
    deleteButton.onclick = () => removeKeyword(listItem, keyword.textContent);
    listItem.appendChild(deleteButton);
    return listItem;
}

function removeKeyword(listItem, keywordText) {
    const availableKeywords = document.getElementById("available-keywords");
    const sortableList = document.getElementById("sortable-container"); // Make sure to get the current instance
    const numberingList = document.getElementById("numbering-list"); // Make sure to get the current instance

    const keywordElement = createKeywordElement(keywordText);
    keywordElement.onclick = () => moveKeywordToSortable(keywordElement, sortableList, numberingList); // Corrected to use keywordElement
    availableKeywords.appendChild(keywordElement);
    listItem.remove();
    updateNumbering(numberingList, sortableList);
}

function updateNumbering(numberingList, sortableList) {
    numberingList.innerHTML = '';
    Array.from(sortableList.children).forEach((item, index) => {
        numberingList.appendChild(createNumberItem(index));
    });
}

function createNumberItem(index) {
    const numberItem = document.createElement("li");
    numberItem.className = "flex items-center justify-center w-10 h-10 bg-white border border-gray-200 rounded text-sm font-medium text-gray-600 mb-2";
    numberItem.textContent = index + 1;
    return numberItem;
}

let sortableInstance = null;
function ensureSortable(sortableList) {
    if (!sortableInstance) {
        sortableInstance = new Sortable(sortableList, {
            animation: 100,
            ghostClass: ['bg-blue-100', 'opacity-75', 'rounded-md'],
            chosenClass: ['bg-blue-300', 'opacity-75'],
            onSort: () => updateNumbering(document.getElementById("numbering-list"), sortableList)
        });
    }
}

function setupSubmitAction() {
    document.getElementById("submit-keywords").addEventListener("click", () => {
        console.log("Submit button clicked.");
        const orderedKeywords = Array.from(document.getElementById("sortable-container").children)
                                    .map((item, index) => {
                                        return { name: item.querySelector('span').textContent.trim(), priority: index + 1 };
                                    });
        console.log("Ordered keywords:", orderedKeywords);
        submitKeywords(orderedKeywords);
    });
}

function submitKeywords(keywords) {
    // Check if keywords are not provided or the array is empty
    if (!keywords || keywords.length === 0) {
        console.error("No keywords submitted.");
        alert("Please select at least one keyword before submitting.");
        return; // Stop the function if no keywords
    }

    console.log("Submitting keywords:", keywords);
    fetch("submit-keyword-order/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ordered_keywords: keywords })
    })
    .then(response => {
        console.log("Response received.");
        return response.json();
    })
    .then(data => {
        console.log("Response data:", data);
        if (data.success) {
            console.log("Success: Redirecting to", data.redirect_url);
            window.location.href = data.redirect_url;
        } else {
            console.log("Error: There was an error processing the request.");
            alert("There was an error processing your request.");
        }
    })
    .catch(error => {
        console.error("An error occurred:", error);
        alert("An error occurred while processing your request.");
    });
}
