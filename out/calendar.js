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
