"""
СИСТЕМА НЕЧЁТКОГО УПРАВЛЕНИЯ ДВИЖЕНИЕМ БЕСПИЛОТНОГО АВТОМОБИЛЯ
-----------------------------------------------------------------
1. Хранение базы знаний (правил) в Neo4j
2. Извлечение правил
3. Реализация нечеткой логики управления скоростью
4. Симуляция движения по маршруту
"""

from neo4j import GraphDatabase
import numpy as np
import skfuzzy as fuzz
from skfuzzy import control as ctrl
import random
import time


# ============================================================
# 1. Подключение к Neo4j и создание базы знаний
# ============================================================

URI = "bolt://localhost:7687"
AUTH = ("neo4j", "12345678")


driver = GraphDatabase.driver(URI, auth=AUTH)

# Определим правила управления
rules = [
    {
        "id": "R1",
        "conditions": [{"name": "road", "value": "скользко"},
                       {"name": "obstacle", "value": "близко"}],
        "actions": [{"name": "speed", "value": "замедлить"}]
    },
    {
        "id": "R2",
        "conditions": [{"name": "weather", "value": "дождь"},
                       {"name": "road", "value": "мокро"}],
        "actions": [{"name": "speed", "value": "замедлить"}]
    },
    {
        "id": "R3",
        "conditions": [{"name": "road", "value": "сухо"},
                       {"name": "weather", "value": "ясно"},
                       {"name": "obstacle", "value": "далеко"}],
        "actions": [{"name": "speed", "value": "ускорить"}]
    },
    {
        "id": "R4",
        "conditions": [{"name": "obstacle", "value": "близко"}],
        "actions": [{"name": "speed", "value": "замедлить"}]
    },
    {
        "id": "R5",
        "conditions": [{"name": "road", "value": "мокро"}],
        "actions": [{"name": "speed", "value": "ровно"}]
    }
]



def create_rule(tx, rule):
    """Создание одного правила в Neo4j"""
    tx.run("CREATE (r:Rule {id:$id})", id=rule["id"])
    for cond in rule["conditions"]:
        tx.run("""
            MATCH (r:Rule {id:$rid})
            CREATE (r)-[:HAS_CONDITION]->(:Condition {name:$name, value:$value})
        """, rid=rule["id"], name=cond["name"], value=cond["value"])
    for act in rule["actions"]:
        tx.run("""
            MATCH (r:Rule {id:$rid})
            CREATE (r)-[:HAS_ACTION]->(:Action {name:$name, value:$value})
        """, rid=rule["id"], name=act["name"], value=act["value"])


with driver.session() as session:
    session.run("MATCH (n) DETACH DELETE n")  # Очистка БД
    for rule in rules:
        session.execute_write(create_rule, rule)
print("✅ База знаний успешно создана в Neo4j.\n")


# ============================================================
# 2. Загрузка правил из Neo4j
# ============================================================

def load_rules(tx):
    query = """
    MATCH (r:Rule)-[:HAS_CONDITION]->(c:Condition),
          (r)-[:HAS_ACTION]->(a:Action)
    RETURN r.id as rule_id, collect(c{.name,.value}) as conditions, 
           collect(a{.name,.value}) as actions
    """
    return [record.data() for record in tx.run(query)]


with driver.session() as session:
    loaded_rules = session.execute_read(load_rules)

print("📘 Загруженные правила из Neo4j:")
for rule in loaded_rules:
    print(rule)
print()


# ============================================================
# 3. Реализация нечеткой логики
# ============================================================

# Входные переменные
weather = ctrl.Antecedent(np.arange(0, 11, 1), 'weather')
road = ctrl.Antecedent(np.arange(0, 11, 1), 'road')
obstacle = ctrl.Antecedent(np.arange(0, 101, 1), 'obstacle')

# Выходная переменная
speed = ctrl.Consequent(np.arange(-10, 11, 1), 'speed')

# Функции принадлежности
weather['clear'] = fuzz.trimf(weather.universe, [0, 0, 4])
weather['rain'] = fuzz.trimf(weather.universe, [4, 7, 10])

road['dry'] = fuzz.trimf(road.universe, [0, 0, 4])
road['wet'] = fuzz.trimf(road.universe, [4, 7, 10])
road['slippery'] = fuzz.trimf(road.universe, [6, 10, 10])

obstacle['far'] = fuzz.trimf(obstacle.universe, [50, 100, 100])
obstacle['close'] = fuzz.trimf(obstacle.universe, [0, 0, 30])

speed['decrease'] = fuzz.trimf(speed.universe, [-10, -10, 0])
speed['stable'] = fuzz.trimf(speed.universe, [-2, 0, 2])
speed['increase'] = fuzz.trimf(speed.universe, [0, 10, 10])

# Правила нечеткой логики
rule1 = ctrl.Rule(road['slippery'] & obstacle['close'], speed['decrease'])
rule2 = ctrl.Rule(weather['rain'] & road['wet'], speed['decrease'])
rule3 = ctrl.Rule(road['dry'] & weather['clear'] & obstacle['far'], speed['increase'])
rule4 = ctrl.Rule(obstacle['close'], speed['decrease'])
rule5 = ctrl.Rule(road['wet'], speed['stable'])

# Создаём контроллер
speed_ctrl = ctrl.ControlSystem([rule1, rule2, rule3, rule4, rule5])
speed_sim = ctrl.ControlSystemSimulation(speed_ctrl)


# ============================================================
# 4. Симуляция движения беспилотного автомобиля
# ============================================================

car_speed = 50.0  # начальная скорость (км/ч)
steps = 10        # количество шагов симуляции

print("🚗 Начало симуляции движения:\n")

for step in range(1, steps + 1):
    # случайные входные данные
    w = random.randint(0, 10)
    r = random.randint(0, 10)
    o = random.randint(0, 100)

    speed_sim.input['weather'] = min(max(w, 0), 10)
    speed_sim.input['road'] = min(max(r, 0), 10)
    speed_sim.input['obstacle'] = min(max(o, 0), 100)

    try:
        speed_sim.compute()
        delta = speed_sim.output.get('speed', 0)  # безопасно
    except Exception as e:
        print(f"Ошибка на шаге {step}: {e}")
        delta = 0

    car_speed += delta
    car_speed = max(0, car_speed)

    print(f"Шаг {step:2}: погода={w:2}, дорога={r:2}, препятствие={o:3} → Δv={delta:6.2f}, скорость={car_speed:6.1f} км/ч")


    time.sleep(0.5)

print("\n✅ Симуляция завершена.")
driver.close()
