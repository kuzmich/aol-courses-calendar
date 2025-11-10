const infoBox = document.querySelector('.event-details');
const closeBtn = document.querySelector('button.close');
const events = document.querySelectorAll('.event');
const headerField = document.querySelector('.event-details h3');
const datesField = document.querySelector('[data-name="dates"]');
const placeField = document.querySelector('[data-name="place"]');
const teachersField = document.querySelector('[data-name="teachers"]');
const peopleField = document.querySelector('[data-name="people"]');

for (let event of events) {
    event.addEventListener("click", (e) => {
	const btn = e.target;
	headerField.innerText = btn.dataset.name;
	datesField.innerText = btn.dataset.dates;
	placeField.innerText = btn.dataset.place;
	teachersField.innerText = btn.dataset.teachers;
	peopleField.innerText = btn.dataset.people;
	infoBox.showModal();
    })
}

closeBtn.addEventListener("click", () => {
    infoBox.close();
})

const tabsList = document.querySelector("nav ul");
const tabButtons = tabsList.querySelectorAll("a");
const tabPanels = document.querySelectorAll("section[aria-labelledby]");

tabsList.setAttribute("role", "tablist");

tabPanels.forEach((panel) => {
    panel.setAttribute("role", "tabpanel");
})

tabsList.querySelectorAll("li").forEach((listitem) => {
  listitem.setAttribute("role", "presentation");
});

tabButtons.forEach((tab, index) => {
    tab.setAttribute("role", "tab");
    if (index === 0) {
	tab.setAttribute("aria-selected", true);
    } else {
	tabPanels[index].setAttribute("hidden", "");
    }
})

for (let btn of tabButtons) {
    btn.addEventListener("click", (e) => {
	e.preventDefault();

	const newTab = e.target;
	const activeCalendarId = newTab.getAttribute('href');
	const activeCalendar = document.querySelector(activeCalendarId);

	tabButtons.forEach((tab, index) => {
	    tab.setAttribute("aria-selected", false);
	})

	tabPanels.forEach((panel) => {
	    panel.setAttribute("hidden", true);
	})

	activeCalendar.removeAttribute("hidden");
	newTab.setAttribute("aria-selected", true);
    })
}
