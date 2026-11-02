import os

from typesafe_sdk import TypeSafeClient

from mergechat.jev.prompts import build_questions


def checkMessage(ticket: str):
    with TypeSafeClient(
        base_url="https://polza.ai/api",
        api_key=os.environ.get("MERGECHAT_JEV_API_KEY"),
        compression=False,
    ) as client:
        return client.system_one(
            state=ticket,
            questions=build_questions(),
        )
def print_answers(state):
    response = checkMessage(state)
    print(state)
    print("is_animal_transport:", response.answers.get("is_animal_transport").noul)
    print("is_order:", response.answers.get("is_order").noul)
    print("animal_type:", response.answers.get("animal_type").choice)
    print("headcount:", response.answers.get("headcount").choice)
    print("capacity_fit:", response.answers.get("capacity_fit").choice)
    print("has_route:", response.answers.get("has_route").noul)
    print("quote_only:", response.answers.get("quote_only").noul)
    print("-" * 40)

def main() -> None:
    api_key = os.environ.get("MERGECHAT_JEV_API_KEY")
    if not api_key:
        raise RuntimeError("Set MERGECHAT_JEV_API_KEY before running the JEV sandbox.")

    print_answers({
    "conversation": {
        "thread_id": "chat-8842",
        "messages": [
            {
                "nickname": "alex_92",
                "timestamp": "2026-10-18T14:03:12Z",
                "text": "Hello"
            },
            {
                "nickname": "support_maria",
                "timestamp": "2026-10-18T14:05:47Z",
                "text": "Hello need transport horses from Moscow to St. Petersburg on June 15. "
            },
            {
                "nickname": "alex_92",
                "timestamp": "2026-10-18T14:07:03Z",
                "text": "Wow, its me"
            }
        ]
    }
})
    # print_answers("Здравствуйте. Требуется перевозка 6 лошадей из Москвы в Санкт-Петербург 15 июня. Прошу рассчитать стоимость и подтвердить возможность.")
    # print_answers("Добрый день! Нужна транспортировка 2 голов крупного рогатого скота из Казани в Самару на следующей неделе. Есть ли свободный прицеп?")
    # print_answers("Прошу организовать перевозку 8 лошадей и 2 собак из Екатеринбурга в Челябинск 20 июля. Требуется коневозка и прицеп.")
    # print_answers("Здравствуйте. Интересует перевозка 1 лошади из Новосибирска в Омск. Дата: 10 августа. Контактный телефон: +7...")
    # print_answers("Компания «АгроТранс» просит предоставить коммерческое предложение на перевозку 4 лошадей из Воронежа в Липецк 5 сентября. Груз готов к погрузке.")
    # print_answers("Привет! Надо перевезти двух коняг из Питера в Москву. Сколько будет стоить? Когда сможете?")
    # print_answers("Здарова, есть 8 лошадей, надо перекинуть из деревни в город. Коневозка есть? Срочно!")
    # print_answers("Слушай, нужно перевезти кота и собаку, но у меня нет машины. Можешь помочь? Из Тулы в Калугу.")
    # print_answers("Перевозка 8 лошадей. Маршрут: Москва — Санкт-Петербург. Дата: 15.06.")
    # print_answers("Требуется транспорт для 2 голов. Животные: лошади. Направление: Казань — Самара.")
    # print_answers("Наличие свободного прицепа на 2 головы. Интересует перевозка КРС.")
    # print_answers("Заявка: 4 лошади, Воронеж — Липецк, 05.09. Без контактов.")