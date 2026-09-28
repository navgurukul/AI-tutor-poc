# Groundedness run — qwen35-multibook

2026-09-28T08:17:37+00:00 · tutor `qwen3.5:2b-q4_K_M` · http://127.0.0.1:8756 · budget backend default · judge gemma3:4b (local, via Ollama)

Gold set `docs/groundedness/evalset-multibook.json` over *NCERT Class 5 EVS (Looking Around), NCERT Class 6 Science, NCERT Class 8 Science, NCERT Class 9 Science, NCERT Class 9 English (Beehive) and NCERT Class 10 Science*. Each answer is graded against the excerpt block that turn actually read, not against the pages it cited.

## Headline

| | |
|---|---|
| Groundedness (claims) | **84%** (62/74 claims supported) |
| Groundedness (per turn) | 84% |
| Contradictions | **4** claims, in 3 of 14 turns |
| Unsupported | 8 claims |
| Key coverage | 75% |
| Context recall | 68% of gold passages reached the prompt |
| Fully grounded turns | 6/14 |
| Supported on a quote not in the excerpt | 3 — judge slips, check by hand |
| Off-syllabus abstention | not in this run |

| outcome | turns |
|---|---|
| grounded and complete | 6 |
| contradicts the book | 3 |
| right, but not from the book | 3 |
| grounded but thin | 2 |

## The judge, graded first

12/14 known verdicts correct. It missed real support 0% of the time and waved a false claim through 22% of the time — the error bars on every number above.

| statement | expected | judge said |
|---|---|---|
| Density is the volume of a substance divided by its mass. | contradicted | supported |
| The density of pure water is one gram per cubic centimetre. | unsupported | supported |

## Per item

| item | grounded | key | recall | claims | outcome |
|---|---|---|---|---|---|
| `M1-ant-smell` | 67% | 50% | 100% | 9 | right, but not from the book |
| `M2-herbivores` | 50% | 50% | 0% | 6 | contradicts the book |
| `M3-nutrients` | 83% | 100% | 0% | 6 | contradicts the book |
| `M4-crop` | 80% | 50% | 100% | 5 | grounded and complete |
| `M5-kharif-rabi` | 100% | 100% | 100% | 5 | grounded and complete |
| `M6-tilling` | 100% | 100% | 100% | 6 | grounded and complete |
| `M7-density` | 100% | 100% | 0% | 5 | grounded and complete |
| `M8-melting-point` | 100% | 100% | 100% | 5 | grounded and complete |
| `M9-combination` | 100% | 0% | 100% | 4 | grounded but thin |
| `M10-exothermic` | 75% | 100% | 100% | 4 | right, but not from the book |
| `M11-displacement` | 80% | 100% | 0% | 5 | contradicts the book |
| `M12-participial` | 80% | 100% | 100% | 5 | grounded and complete |
| `M13-crop-classified` | 100% | 0% | 50% | 6 | grounded but thin |
| `M14-exothermic-example` | 67% | 100% | 100% | 3 | right, but not from the book |

---

### `M1-ant-smell` — How do ants find their way?

**Retrieved:** 2 · **read:** 1 passage(s), 597 chars · **gold pages:** p.3 · **cited:** p.2, p.3

**Gold passage reached the prompt:** 1/1 quotes

**Answer**

> Ants use a special sense called pheromones to find food. When an ant moves forward, it leaves a faint smell on the ground behind it. Other ants can follow this scent trail just like you might follow a path in the rain. This happens because they are very good at smelling things out. The ants do not need to see the food; they simply follow the smell until they reach their destination.
> 
> Imagine walking down a long hallway where your friend is holding a flashlight. You can see the light, but if you were blind, you would have to follow the light's path until you find the end of the hall. The ants work exactly like that, using the scent trail as their "light" to navigate through the forest.
> 
> This shows how animals help each other by sharing information without needing to talk. It is a very important skill for ants because it helps them save time and energy while searching for food.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| Ants use a special sense called pheromones to find food. | supported | He found out that as the ants move, they leave a smell on the ground. The other ants follow the smell to find the way. |
| When an ant moves forward, it leaves a faint smell on the ground behind it. | supported | He found out that as the ants move, they leave a smell on the ground. |
| Other ants can follow this scent trail just like you might follow a path in the rain. | supported | He found out that as the ants move, they leave a smell on the ground. The other ants follow the smell to find the way. |
| This happens because they are very good at smelling things out. | supported | The other ants follow the smell to find the way. |
| The ants do not need to see the food; they simply follow the smell until they reach their destination. | supported | He found out that as the ants move, they leave a smell on the ground. The other ants follow the smell to find the way. |
| You can see the light, but if you were blind, you would have to follow the light's path until you find the end of the hall. | **unsupported** | Dogs mark out their own area on the road. They can make out if another dog has come into their area by the smell of its urine or potty (latrine). |
| The ants work exactly like that, using the scent trail as their "light" to navigate through the forest. | **unsupported** | The other ants follow the smell to find the way. |
| This shows how animals help each other by sharing information without needing to talk. | supported | He found out that as the ants move, they leave a smell on the ground. The other ants follow the smell to find the way. |
| It is a very important skill for ants because it helps them save time and energy while searching for food. | **unsupported** | The other ants follow the smell to find the way. |

*Not scored (1 sentence(s) asserting nothing):* invitation — Imagine walking down a long hallway where your friend is holding a flashlight.

**What the book answers with:** ✗ ants leave a smell on the ground · ✓ other ants follow that smell

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 5 EVS (Looking Around) - pp. 3-4
… He found out that as the ants move, they leave a smell on the ground. The other ants follow the smell to find the way. Now carefully, without harming the ants, block their path for a while with a pencil. /rhombus4Now observe, how do the ants move? /rhombus4Have you seen a dog snif fing here and there? What do you think it is trying to smell? Dogs mark out their own area on the road. They can make out if another dog has come into their area by the smell of its urine or potty (latrine). /rhombus4Do you and your friends have similar answers? …
```
</details>

---

### `M2-herbivores` — What are herbivores and carnivores?

**Retrieved:** 2 · **read:** 1 passage(s), 631 chars · **gold pages:** p.6 · **cited:** p.5, p.6

**Gold passage reached the prompt:** 0/3 quotes

**Answer**

> Herbivores are animals that eat only plants or plant products, while carnivores are animals that eat other living animals. Some creatures belong to both groups depending on what they consume at a given time. This classification helps scientists understand how different species survive in nature by matching their diet with available food sources. For example, cows and deer fall into the herbivore category because they feed exclusively on grasses and leaves. In contrast, lions and tigers are carnivores since they hunt down and eat meat from other animals. By grouping animals this way, we can better predict how ecosystems balance out over time.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| Herbivores are animals that eat only plants or plant products, while carnivores are animals that eat other living animals. | **CONTRADICTED** | known error: p.6 says herbivores eat only plants |
| Some creatures belong to both groups depending on what they consume at a given time. | **CONTRADICTED** | Place animals which eat only plants or plant products in Group 1. These are called herbivores . There are some animals which eat other animals. Place these in Group 2. These animal |
| This classification helps scientists understand how different species survive in nature by matching their diet with available food sources. | supported | Place animals which eat only plants or plant products in Group 1. These are called herbivores . There are some animals which eat other animals. Place these in Group 2. These animal |
| For example, cows and deer fall into the herbivore category because they feed exclusively on grasses and leaves. | supported | For some of them, the type of food they eat is also given. Fill in the blanks in the table. Have a look again at Table 1.5 and group the animals entered here as follows. Place anim |
| In contrast, lions and tigers are carnivores since they hunt down and eat meat from other animals. | supported | Place animals which eat only plants or plant products in Group 1. These are called herbivores . There are some animals which eat other animals. Place these in Group 2. These animal |
| By grouping animals this way, we can better predict how ecosystems balance out over time. | **unsupported** | Place animals which eat only plants or plant products in Group 1. These are called herbivores . There are some animals which eat other animals. Place these in Group 2. These animal |

**What the book answers with:** ✓ herbivores eat only plants · ✗ carnivores eat only animals

**Known error fired:** p.6 says herbivores eat only plants

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 6 Science - PRODUCTS AS FOOD - p. 5
… For some of them, the type of food they eat is also given. Fill in the blanks in the table. Have a look again at Table 1.5 and group the animals entered here as follows. Place animals which eat only plants or plant products in Group 1. These are called herbivores . There are some animals which eat other animals. Place these in Group 2. These animals are called carnivores . Do you find some animals which eat both plants and animals? Place them in Group 3. These are called omnivores. Prepare a table as in Table 1.6 and enter these separately in the three columns, as shown.
```
</details>

---

### `M3-nutrients` — What are nutrients?

**Retrieved:** 2 · **read:** 1 passage(s), 580 chars · **gold pages:** p.8 · **cited:** p.8, p.16

**Gold passage reached the prompt:** 0/1 quotes

**Answer**

> Nutrients are essential substances found in food that provide energy, support growth, and keep the body healthy. These vital components include carbohydrates, proteins, fats, vitamins, minerals, dietary fibers, and water. The primary role of these nutrients is to fuel our bodies for daily activities while also helping us build strong muscles and organs. Without enough nutrients, a person cannot grow properly or maintain their health effectively.
> 
> Think about how you need rice and bread to survive, as both contain carbohydrates that give your body the energy needed to function. Another example is drinking milk because it provides proteins that help your body repair itself after an illness. Understanding this helps explain why eating balanced meals is so important for keeping everyone strong and healthy in our daily lives.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| Nutrients are essential substances found in food that provide energy, support growth, and keep the body healthy. | supported | The major nutrients in our food are carbohydrates, proteins, fats, vitamins and minerals. |
| These vital components include carbohydrates, proteins, fats, vitamins, minerals, dietary fibers, and water. | supported | The major nutrients in our food are carbohydrates, proteins, fats, vitamins and minerals. In addition, food also contains dietary fibres and water. |
| The primary role of these nutrients is to fuel our bodies for daily activities while also helping us build strong muscles and organs. | supported | Carbohydrates and fats mainly provide energy to our body. |
| Without enough nutrients, a person cannot grow properly or maintain their health effectively. | supported | Proteins and minerals are needed for the growth and the maintenance of our body. |
| Another example is drinking milk because it provides proteins that help your body repair itself after an illness. | **CONTRADICTED** | Vitamins help in protecting our body against diseases. |
| Understanding this helps explain why eating balanced meals is so important for keeping everyone strong and healthy in our daily lives. | supported | Carbohydrates and fats mainly provide energy to our body. Proteins and minerals are needed for the growth and the maintenance of our body. Vitamins help in protecting our body agai |

*Not scored (1 sentence(s) asserting nothing):* invitation — Think about how you need rice and bread to survive, as both contain carbohydrates that give your body the energy needed to function.

**What the book answers with:** ✓ the major nutrients are carbohydrates, proteins, fats, vitamins and minerals

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 6 Science - DEFICIENCY DISEASES - p. 16
1 Vy , Vs , , /square6 /square6/square6 /square6/square6The major nutrients in our food are carbohydrates, proteins, fats, vitamins and minerals. In addition, food also contains dietary fibres and water. /square6 /square6/square6/square6/square6Carbohydrates and fats mainly provide energy to our body. /square6 /square6/square6 /square6/square6Proteins and minerals are needed for the growth and the maintenance of our body. /square6 /square6/square6 /square6/square6Vitamins help in protecting our body against diseases. …
```
</details>

---

### `M4-crop` — What is a crop?

**Retrieved:** 2 · **read:** 1 passage(s), 649 chars · **gold pages:** p.1 · **cited:** p.1, p.2

**Gold passage reached the prompt:** 1/1 quotes

**Answer**

> A crop is simply the name given to plants grown on a large scale in a single place for many years at once. This specific term comes from the word "crop," which means the harvest of those plants. You already know that there are different kinds of crops, such as cereals like wheat or vegetables, and they can be sorted by whether they grow during hot seasons or rainy periods. Because India is a very large country with many regions, the weather changes from one area to another, so farmers must choose which type of plant fits their local climate best. All living things need food to survive, and since plants make their own food using sunlight, rain, and soil nutrients, they are considered self-sufficient organisms that do not rely on other animals for nutrition.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| A crop is simply the name given to plants grown on a large scale in a single place for many years at once. | supported | When plants of the same kind are cultivated at one place on a large scale, it is called a crop. |
| This specific term comes from the word "crop," which means the harvest of those plants. | supported | When plants of the same kind are cultivated at one place on a large scale, it is called a crop. For example, crop of wheat means that all the plants grown in a field are that of wh |
| You already know that there are different kinds of crops, such as cereals like wheat or vegetables, and they can be sorted by whether they grow during hot seasons or rainy periods. | supported | When plants of the same kind are cultivated at one place on a large scale, it is called a crop. For example, crop of wheat means that all the plants grown in a field are that of wh |
| Because India is a very large country with many regions, the weather changes from one area to another, so farmers must choose which type of plant fits their local climate best. | supported | India is a vast country. The climatic conditions like temperature, humidity and rainfall vary from one region to another. |
| All living things need food to survive, and since plants make their own food using sunlight, rain, and soil nutrients, they are considered self-sufficient organisms that do not rely on other animals for nutrition. | **unsupported** | Plants can make their food themselves. |

**What the book answers with:** ✗ a crop is plants of the same kind grown at one place on a large scale · ✓ grown on a large scale

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 8 Science - Agricultural Practices - p. 1
When plants of the same kind are cultivated at one place on a large scale, it is called a crop. For example, crop of wheat means that all the plants grown in a field are that of wheat. You already know that crops are of different types like cereals, vegetables and fruits. These can be classified on the basis of the season in which they grow. India is a vast country. The climatic conditions like temperature, humidity and rainfall vary from one region to another. Accordingly, there is a rich You have learnt that all living organisms require food. Plants can make their food themselves. …
```
</details>

---

### `M5-kharif-rabi` — What is the difference between kharif and rabi crops?

**Retrieved:** 2 · **read:** 1 passage(s), 516 chars · **gold pages:** p.2 · **cited:** p.2, p.15

**Gold passage reached the prompt:** 2/2 quotes

**Answer**

> Kharif and Rabi crops are simply two categories of plants that farmers grow based on when they plant them in a year. The main difference lies in the time of year you sown these seeds, which determines where they grow and what kind of food they produce. Kharif crops are planted during the rainy season, typically from June to September, while Rabi crops are grown in the cooler winter months between October and March. Because these two seasons have opposite weather conditions, farmers must choose specific plants for each time frame to ensure a good harvest. For example, paddy is considered a kharif crop because it needs water during the monsoon rains, whereas wheat belongs to the rabi group since it thrives in dry winter days.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| Kharif and Rabi crops are simply two categories of plants that farmers grow based on when they plant them in a year. | supported | The crops which are sown in the rainy season are called kharif crops. The rainy season in India is generally from June to September . Paddy, maize, soyabean, groundnut and cotton a |
| The main difference lies in the time of year you sown these seeds, which determines where they grow and what kind of food they produce. | supported | The crops which are sown in the rainy season are called kharif crops. The rainy season in India is generally from June to September . Paddy, maize, soyabean, groundnut and cotton a |
| Kharif crops are planted during the rainy season, typically from June to September, while Rabi crops are grown in the cooler winter months between October and March. | supported | Kharif Crops : The crops which are sown in the rainy season are called kharif crops. The rainy season in India is generally from June to September . Paddy, maize, soyabean, groundn |
| Because these two seasons have opposite weather conditions, farmers must choose specific plants for each time frame to ensure a good harvest. | supported | The rainy season in India is generally from June to September . |
| For example, paddy is considered a kharif crop because it needs water during the monsoon rains, whereas wheat belongs to the rabi group since it thrives in dry winter days. | supported | Paddy, maize, soyabean, groundnut and cotton are kharif crops. |

**What the book answers with:** ✓ kharif crops are sown in the rainy season · ✓ rabi crops are grown in the winter season

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 8 Science - Agricultural Practices - p. 2
(i) Kharif Crops : The crops which are sown in the rainy season are called kharif crops. The rainy season in India is generally from June to September .

Paddy, maize, soyabean, groundnut and cotton are kharif crops.

(ii) Rabi Crops : The crops grown in the winter season (October to March) are called rabi crops. Examples of rabi crops are wheat, gram, pea, mustard and linseed.

Besides these, pulses and vegetables are grown during summer at many places.
```
</details>

---

### `M6-tilling` — What is tilling?

**Retrieved:** 2 · **read:** 1 passage(s), 624 chars · **gold pages:** p.3 · **cited:** p.3

**Gold passage reached the prompt:** 1/1 quotes

**Answer**

> Tilling is the process of turning and loosening the soil using a tool called a plough. This action breaks up hard clumps of dirt so that crops can grow better underneath them. The plough is typically made of wood or iron, but it must be used carefully because dry soil often needs water before being worked. When you plough a field, you create big crumbs where the soil has been broken apart. It is also very important to level the ground after tilling so that seeds can be planted evenly and irrigation works properly. Sometimes farmers add manure or fertilizer to the soil before beginning this process to help nourish the plants.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| Tilling is the process of turning and loosening the soil using a tool called a plough. | supported | turning and loosening of soil is very important for cultivation of crops. The process of loosening and turning of the soil is called tilling or ploughing. This is done by using a p |
| This action breaks up hard clumps of dirt so that crops can grow better underneath them. | supported | It is necessary to break these crumbs. |
| The plough is typically made of wood or iron, but it must be used carefully because dry soil often needs water before being worked. | supported | Ploughs are made of wood or iron. If the soil is very dry, it may need watering before ploughing. |
| When you plough a field, you create big crumbs where the soil has been broken apart. | supported | The ploughed field may have big clumps of soil called crumbs. |
| It is also very important to level the ground after tilling so that seeds can be planted evenly and irrigation works properly. | supported | Levelling the field is beneficial for sowing as well as for irrigation. |
| Sometimes farmers add manure or fertilizer to the soil before beginning this process to help nourish the plants. | supported | Sometimes, manure is added to the soil before tilling. |

**What the book answers with:** ✓ tilling is loosening and turning the soil

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 8 Science - Preparation of Soil - p. 3
turning and loosening of soil is very important for cultivation of crops. The process of loosening and turning of the soil is called tilling or ploughing. This is done by using a plough. Ploughs are made of wood or iron. If the soil is very dry, it may need watering before ploughing. The ploughed field may have big clumps of soil called crumbs. It is necessary to break these crumbs. Levelling the field is beneficial for sowing as well as for irrigation. Levelling of soil is done with the help of a leveller. Sometimes, manure is added to the soil before tilling. …
```
</details>

---

### `M7-density` — What is density?

**Retrieved:** 2 · **read:** 1 passage(s), 547 chars · **gold pages:** p.6 · **cited:** p.142

**Gold passage reached the prompt:** 0/1 quotes

**Answer**

> Density is defined as the amount of mass contained within a specific unit volume of a substance. This concept explains how heavy or light something feels for its size, which is why gold feels much heavier than water even though it takes up less space. You can think of density like a fingerprint that helps scientists identify if a material is pure or mixed with other things. For instance, the density of gold is 19300 kg m-3 while that of water is 1000 kg m-3. The density of a given sample of a substance can help us to determine its purity.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| Density is defined as the amount of mass contained within a specific unit volume of a substance. | supported | As you know, the density of a substance is defined as mass of a unit volume. |
| This concept explains how heavy or light something feels for its size, which is why gold feels much heavier than water even though it takes up less space. | supported | The density of a given substance, under specified conditions, remains the same. |
| You can think of density like a fingerprint that helps scientists identify if a material is pure or mixed with other things. | supported | The density of a given sample of a substance can help us to determine its purity. |
| For instance, the density of gold is 19300 kg m-3 while that of water is 1000 kg m-3. | supported | The density of a given substance, under specified conditions, remains the same. Therefore the density of a substance is one of its characteristic properties. It is different for di |
| The density of a given sample of a substance can help us to determine its purity. | supported | The density of a given sample of a substance can help us to determine its purity. |

**What the book answers with:** ✓ density is mass per unit volume

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 9 Science - 2BUOYANCY - p. 142
As you know, the density of a substance is defined as mass of a unit volume. The unit of density is kilogram per metre cube (kg m-3). The density of a given substance, under specified conditions, remains the same. Therefore the density of a substance is one of its characteristic properties. It is different for different substances. For example, the density of gold is 19300 kg m-3 while that of water is 1000 kg m-3. The density of a given sample of a substance can help us to determine its purity.
```
</details>

---

### `M8-melting-point` — What is the melting point of a solid?

**Retrieved:** 2 · **read:** 2 passage(s), 808 chars · **gold pages:** p.7 · **cited:** p.7, p.11

**Gold passage reached the prompt:** 2/2 quotes

**Answer**

> A melting point is the specific temperature where a solid turns directly into a liquid without becoming a gas first. This happens when the heat energy added to the solid breaks the strong forces holding its particles together, allowing them to move freely as a liquid. The minimum temperature at which this change occurs under normal atmospheric pressure defines the melting point for that substance. For example, ice melts at 0 degrees Celsius because it reaches this exact threshold where water molecules gain enough energy to break their rigid structure. This concept is crucial because it shows that while heat is added during melting, the temperature of the solid stays constant until all the solid has become liquid.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| A melting point is the specific temperature where a solid turns directly into a liquid without becoming a gas first. | supported | The minimum temperature at which a solid melts to become a liquid at the atmospheric pressure is called its melting point. |
| This happens when the heat energy added to the solid breaks the strong forces holding its particles together, allowing them to move freely as a liquid. | supported | The melting point of a solid is an indication of the strength of the force of attraction between its particles. |
| The minimum temperature at which this change occurs under normal atmospheric pressure defines the melting point for that substance. | supported | A stage is reached when the solid melts and is converted to a liquid. The minimum temperature at which a solid melts to become a liquid at the atmospheric pressure is called its me |
| For example, ice melts at 0 degrees Celsius because it reaches this exact threshold where water molecules gain enough energy to break their rigid structure. | supported | The melting point of ice is 273.15 K* |
| This concept is crucial because it shows that while heat is added during melting, the temperature of the solid stays constant until all the solid has become liquid. | supported | The melting point of a solid is an indication of the strength of the force of attraction between its particles. The melting point of ice is 273.15 K*. The process of melting, that  |

**What the book answers with:** ✓ the melting point is the minimum temperature at which a solid becomes a liquid

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 9 Science - EFFECT OF CHANGE OF TEMPERATURE - p. 7
… A stage is reached when the solid melts and is converted to a liquid. The minimum temperature at which a solid melts to become a liquid at the atmospheric pressure is called its melting point. The melting point of a solid is an indication of the strength of the force of attraction between its particles. The melting point of ice is 273.15 K*. The process of melting, that is, change of solid state into liquid state is also known as fusion. When a solid melts, its temperature remains the same, so where does the heat energy go?

[2] NCERT Class 9 Science - Condensate (BEC). In 2001, Eric A. Cornell, Wolfgang - p. 11
• Latent heat of fusion is the amount of heat energy required to change 1 kg of solid into liquid at its melting point.
```
</details>

---

### `M9-combination` — What is a combination reaction?

**Retrieved:** 2 · **read:** 1 passage(s), 611 chars · **gold pages:** p.6 · **cited:** p.6, p.14

**Gold passage reached the prompt:** 2/2 quotes

**Answer**

> A combination reaction occurs when two or more substances join together to create a single new product. This type of chemical process follows the rule that reactants merge into one unified substance without breaking down into separate parts beforehand. For instance, when quick lime reacts with water, calcium oxide combines directly with water molecules to form slaked lime, which is exactly what happens in this specific reaction described in your textbook. You can picture this as two distinct ingredients mixing perfectly to make a single, stronger dish rather than just being eaten separately.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| A combination reaction occurs when two or more substances join together to create a single new product. | supported | In simple language we can say that when two or more substances (elements or compounds) combine to form a single product, the reactions are called combination reactions. |
| This type of chemical process follows the rule that reactants merge into one unified substance without breaking down into separate parts beforehand. | supported | In simple language we can say that when two or more substances (elements or compounds) combine to form a single product, the reactions are called combination reactions. |
| For instance, when quick lime reacts with water, calcium oxide combines directly with water molecules to form slaked lime, which is exactly what happens in this specific reaction described in your textbook. | supported | In simple language we can say that when two or more substances (elements or compounds) combine to form a single product, the reactions are called combination reactions. |
| You can picture this as two distinct ingredients mixing perfectly to make a single, stronger dish rather than just being eaten separately. | supported | In simple language we can say that when two or more substances (elements or compounds) combine to form a single product, the reactions are called combination reactions. |

**What the book answers with:** ✗ two or more reactants form a single product

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 10 Science - CTIONSCTIONS - pp. 6-7
Formation of slaked lime by the reaction of calcium oxide with water

(Quick lime) (Slaked lime)

In this reaction, calcium oxide and water combine to form a single product, calcium hydroxide. Such a reaction in which a single product is formed from two or more reactants is known as a combination reaction.

Let us discuss some more examples of combination reactions.

(i) Burning of coal

In simple language we can say that when two or more substances (elements or compounds) combine to form a single product, the reactions are called combination reactions.
```
</details>

---

### `M10-exothermic` — What is an exothermic reaction?

**Retrieved:** 2 · **read:** 1 passage(s), 349 chars · **gold pages:** p.7 · **cited:** p.7, p.14

**Gold passage reached the prompt:** 1/1 quotes

**Answer**

> An exothermic reaction is a type of chemical process where heat energy is released and given off to the surroundings as products form. This happens because the bonds formed in the new substances are stronger than the bonds broken in the starting materials, requiring less energy overall. Consequently, the excess energy leaves the system as warmth, which is why you can feel the mixture getting warm after mixing chemicals together.
> 
> For instance, when you light a candle, the chemical reaction between wax and oxygen releases heat that warms your hand; this specific process is an exothermic reaction because it generates thermal energy rather than consuming it.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| An exothermic reaction is a type of chemical process where heat energy is released and given off to the surroundings as products form. | supported | In Activity 1.4, we also observed that a large amount of heat is evolved. This makes the reaction mixture warm. Reactions in which heat is released along with the formation of prod |
| This happens because the bonds formed in the new substances are stronger than the bonds broken in the starting materials, requiring less energy overall. | **unsupported** | In Activity 1.4, we also observed that a large amount of heat is evolved. This makes the reaction mixture warm. Reactions in which heat is released along with the formation of prod |
| Consequently, the excess energy leaves the system as warmth, which is why you can feel the mixture getting warm after mixing chemicals together. | supported | In Activity 1.4, we also observed that a large amount of heat is evolved. This makes the reaction mixture warm. |
| For instance, when you light a candle, the chemical reaction between wax and oxygen releases heat that warms your hand; this specific process is an exothermic reaction because it generates thermal energy rather than consuming it. | supported | In Activity 1.4, we also observed that a large amount of heat is evolved. This makes the reaction mixture warm. Reactions in which heat is released along with the formation of prod |

**What the book answers with:** ✓ heat is released

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 10 Science - CTIONSCTIONS - p. 7
In Activity 1.4, we also observed that a large amount of heat is evolved. This makes the reaction mixture warm. Reactions in which heat is released along with the formation of products are called exothermic chemical reactions.

Other examples of exothermic reactions are -

(i) Burning of natural gas
```
</details>

---

### `M11-displacement` — What is a displacement reaction?

**Retrieved:** 2 · **read:** 1 passage(s), 612 chars · **gold pages:** p.11 · **cited:** p.11, p.14

**Gold passage reached the prompt:** 0/1 quotes

**Answer**

> A displacement reaction happens when one element takes the place of another element in a compound, causing them to swap positions. This occurs because elements naturally want to form their own stable compounds rather than sharing or holding onto others' structures. For instance, if you mix iron filings with copper sulfate solution, the iron will push out the copper from the salt and create new substances like iron oxide and metallic copper.
> 
> This specific example shows how two different atoms exchange roles: the iron atom moves to become part of a new compound while the copper atom leaves its original spot in the solution. The textbook formula Fe2O3 + 2Al → Al2O3 + 2Fe illustrates this perfectly, where aluminum displaces oxygen from iron oxide to form aluminum oxide and free iron metal.
> 
> Think about how you might see this happen if you try mixing a spoonful of baking soda with vinegar; the gas bubbles you see are actually the result of one substance displacing another within the chemical mixture.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| A displacement reaction happens when one element takes the place of another element in a compound, causing them to swap positions. | supported | When an element displaces another element from its compound, a displacement reaction occurs. |
| This occurs because elements naturally want to form their own stable compounds rather than sharing or holding onto others' structures. | **CONTRADICTED** | When an element displaces another element from its compound, a displacement reaction occurs. |
| For instance, if you mix iron filings with copper sulfate solution, the iron will push out the copper from the salt and create new substances like iron oxide and metallic copper. | supported | When an element displaces another element from its compound, a displacement reaction occurs. |
| This specific example shows how two different atoms exchange roles: the iron atom moves to become part of a new compound while the copper atom leaves its original spot in the solution. | supported | Two different atoms or groups of atoms (ions) are exchanged in double displacement reactions. |
| The textbook formula Fe2O3 + 2Al → Al2O3 + 2Fe illustrates this perfectly, where aluminum displaces oxygen from iron oxide to form aluminum oxide and free iron metal. | supported | Fe2O3 + 2Al → Al2O3 + 2Fe |

*Not scored (1 sentence(s) asserting nothing):* invitation — Think about how you might see this happen if you try mixing a spoonful of baking soda with vinegar; the gas bubbles you see are actually the result of one substance displacing another within the chemical mixture.

**What the book answers with:** ✓ one element displaces another from its compound

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 10 Science - Rancidity - p. 14
/square6Reactions in which energy is absorbed are known as endothermic reactions. /square6When an element displaces another element from its compound, a displacement reaction occurs.

/square6Two different atoms or groups of atoms (ions) are exchanged in double displacement reactions.

/square6Precipitation reactions produce insoluble salts.

/square6Reactions also involve the gain or loss of oxygen or hydrogen by substances. Oxidation is the gain of oxygen or loss of hydrogen. Reduction is the loss of oxygen or gain of hydrogen.

2. Fe2O3 + 2Al → Al2O3 + 2Fe
```
</details>

---

### `M12-participial` — What is a participial phrase?

**Retrieved:** 2 · **read:** 1 passage(s), 489 chars · **gold pages:** p.52 · **cited:** p.52, p.77

**Gold passage reached the prompt:** 1/1 quotes

**Answer**

> A participial phrase is a group of words that starts with an -ing verb and describes the person or thing already mentioned in the sentence. It adds extra information about the main subject, showing how they are doing something or what they look like. For example, if you see "The parts in italics begin with -ing verbs," this phrase tells you exactly which words belong to that specific group of letters. You can picture a teacher pointing at a list and saying, "These words all start with an action word," just like how Einstein became a violinist while maintaining his skill throughout his life. This helps the reader understand the relationship between the main idea and the details it provides.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| A participial phrase is a group of words that starts with an -ing verb and describes the person or thing already mentioned in the sentence. | supported | Participial phrases say something more about the person or thing talked about or the idea expressed by the sentence as a whole. |
| It adds extra information about the main subject, showing how they are doing something or what they look like. | supported | Participial phrases say something more about the person or thing talked about or the idea expressed by the sentence as a whole. |
| For example, if you see "The parts in italics begin with -ing verbs," this phrase tells you exactly which words belong to that specific group of letters. | supported | The parts in italics in the above sentences begin with -ing verbs, and are called participial phrases. |
| You can picture a teacher pointing at a list and saying, "These words all start with an action word," just like how Einstein became a violinist while maintaining his skill throughout his life. | **unsupported** | Einstein became a gifted amateur violinist. He maintained this skill throughout his life. |
| This helps the reader understand the relationship between the main idea and the details it provides. | supported | The parts in italics in the above sentences begin with -ing verbs, and are called participial phrases. Participial phrases say something more about the person or thing talked about |

**What the book answers with:** ✓ a participial phrase begins with an -ing verb

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 9 English (Beehive) - / Beehive - p. 52
• Letters survive in which they put their affection into words, mixing science with tenderness.

The parts in italics in the above sentences begin with -ing verbs, and are called participial phrases. Participial phrases say something more about the person or thing talked about or the idea expressed by the sentence as a whole. For example:

- Einstein became a gifted amateur violinist. He maintained this skill throughout his life.
```
</details>

---

### `M13-crop-classified` — How are they classified?

*Asked after* “What is a crop?” *in the same session — the pronoun only resolves because that turn happened.*

**Retrieved:** 2 · **read:** 1 passage(s), 649 chars · **gold pages:** p.1, p.2 · **cited:** p.1, p.15

**Gold passage reached the prompt:** 1/2 quotes

**Answer**

> A crop refers to all plants grown in a field that belong to the same kind or species. This means every plant harvested from that specific area is of the identical type. You can think of this like when you buy wheat flour and know it comes only from wheat plants, not potatoes or corn. In India, because the climate changes so much from one region to another, farmers must choose different crops for different areas based on local weather conditions. For instance, they might plant rice in the wet south while growing wheat in the dry north. This classification helps farmers decide which food will grow best in their specific environment.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| A crop refers to all plants grown in a field that belong to the same kind or species. | supported | When plants of the same kind are cultivated at one place on a large scale, it is called a crop. For example, crop of wheat means that all the plants grown in a field are that of wh |
| This means every plant harvested from that specific area is of the identical type. | supported | When plants of the same kind are cultivated at one place on a large scale, it is called a crop. For example, crop of wheat means that all the plants grown in a field are that of wh |
| You can think of this like when you buy wheat flour and know it comes only from wheat plants, not potatoes or corn. | supported | When plants of the same kind are cultivated at one place on a large scale, it is called a crop. For example, crop of wheat means that all the plants grown in a field are that of wh |
| In India, because the climate changes so much from one region to another, farmers must choose different crops for different areas based on local weather conditions. | supported | India is a vast country. The climatic conditions like temperature, humidity and rainfall vary from one region to another. |
| For instance, they might plant rice in the wet south while growing wheat in the dry north. | supported | India is a vast country. The climatic conditions like temperature, humidity and rainfall vary from one region to another. |
| This classification helps farmers decide which food will grow best in their specific environment. | supported | India is a vast country. The climatic conditions like temperature, humidity and rainfall vary from one region to another. |

**What the book answers with:** ✗ crops are classified by the season in which they grow

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 8 Science - Agricultural Practices - p. 1
When plants of the same kind are cultivated at one place on a large scale, it is called a crop. For example, crop of wheat means that all the plants grown in a field are that of wheat. You already know that crops are of different types like cereals, vegetables and fruits. These can be classified on the basis of the season in which they grow. India is a vast country. The climatic conditions like temperature, humidity and rainfall vary from one region to another. Accordingly, there is a rich You have learnt that all living organisms require food. Plants can make their food themselves. …
```
</details>

---

### `M14-exothermic-example` — Can you give me an example of one?

*Asked after* “What is an exothermic reaction?” *in the same session — the pronoun only resolves because that turn happened.*

**Retrieved:** 2 · **read:** 1 passage(s), 349 chars · **gold pages:** p.7 · **cited:** p.7

**Gold passage reached the prompt:** 1/1 quotes

**Answer**

> An exothermic reaction is a chemical process where heat energy is released into the surroundings as products form. This happens because the bonds formed in the new substances are stronger than the bonds broken in the original ones, causing the excess energy to leave the system. A common everyday example of this is burning natural gas, which warms up the room while producing carbon dioxide and water vapor.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| An exothermic reaction is a chemical process where heat energy is released into the surroundings as products form. | supported | In Activity 1.4, we also observed that a large amount of heat is evolved. This makes the reaction mixture warm. Reactions in which heat is released along with the formation of prod |
| This happens because the bonds formed in the new substances are stronger than the bonds broken in the original ones, causing the excess energy to leave the system. | **unsupported** | In Activity 1.4, we also observed that a large amount of heat is evolved. This makes the reaction mixture warm. Reactions in which heat is released along with the formation of prod |
| A common everyday example of this is burning natural gas, which warms up the room while producing carbon dioxide and water vapor. | supported | In Activity 1.4, we also observed that a large amount of heat is evolved. This makes the reaction mixture warm. Reactions in which heat is released along with the formation of prod |

**What the book answers with:** ✓ burning of natural gas is an example

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 10 Science - CTIONSCTIONS - p. 7
In Activity 1.4, we also observed that a large amount of heat is evolved. This makes the reaction mixture warm. Reactions in which heat is released along with the formation of products are called exothermic chemical reactions.

Other examples of exothermic reactions are -

(i) Burning of natural gas
```
</details>

