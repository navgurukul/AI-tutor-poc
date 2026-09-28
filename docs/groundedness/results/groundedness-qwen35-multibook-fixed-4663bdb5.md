# Groundedness run — qwen35-multibook-fixed

2026-09-28T09:36:50+00:00 · tutor `qwen3.5:2b-q4_K_M` · http://127.0.0.1:8756 · budget backend default · judge gemma3:4b (local, via Ollama)

Gold set `docs/groundedness/evalset-multibook.json` over *NCERT Class 5 EVS (Looking Around), NCERT Class 6 Science, NCERT Class 8 Science, NCERT Class 9 Science, NCERT Class 9 English (Beehive) and NCERT Class 10 Science*. Each answer is graded against the excerpt block that turn actually read, not against the pages it cited.

## Headline

| | |
|---|---|
| Groundedness (claims) | **88%** (69/78 claims supported) |
| Groundedness (per turn) | 87% |
| Contradictions | **4** claims, in 4 of 14 turns |
| Unsupported | 5 claims |
| Key coverage | 75% |
| Context recall | 80% of gold passages reached the prompt |
| Fully grounded turns | 7/14 |
| Supported on a quote not in the excerpt | 4 — judge slips, check by hand |
| Off-syllabus abstention | not in this run |

| outcome | turns |
|---|---|
| grounded and complete | 8 |
| contradicts the book | 4 |
| grounded but thin | 1 |
| right, but not from the book | 1 |

## The judge, graded first

12/14 known verdicts correct. It missed real support 0% of the time and waved a false claim through 22% of the time — the error bars on every number above.

| statement | expected | judge said |
|---|---|---|
| Density is the volume of a substance divided by its mass. | contradicted | supported |
| The density of pure water is one gram per cubic centimetre. | unsupported | supported |

## Per item

| item | grounded | key | recall | claims | outcome |
|---|---|---|---|---|---|
| `M1-ant-smell` | 88% | 50% | 100% | 8 | grounded and complete |
| `M2-herbivores` | 75% | 50% | 67% | 4 | contradicts the book |
| `M3-nutrients` | 100% | 100% | 0% | 7 | grounded and complete |
| `M4-crop` | 86% | 50% | 100% | 7 | contradicts the book |
| `M5-kharif-rabi` | 100% | 100% | 100% | 5 | grounded and complete |
| `M6-tilling` | 100% | 100% | 100% | 5 | grounded and complete |
| `M7-density` | 100% | 100% | 0% | 5 | grounded and complete |
| `M8-melting-point` | 100% | 100% | 100% | 5 | grounded and complete |
| `M9-combination` | 100% | 0% | 100% | 5 | grounded but thin |
| `M10-exothermic` | 60% | 0% | 100% | 5 | contradicts the book |
| `M11-displacement` | 88% | 100% | 100% | 8 | grounded and complete |
| `M12-participial` | 60% | 100% | 100% | 5 | contradicts the book |
| `M13-crop-classified` | 100% | 100% | 50% | 6 | grounded and complete |
| `M14-exothermic-example` | 67% | 100% | 100% | 3 | right, but not from the book |

---

### `M1-ant-smell` — How do ants find their way?

**Retrieved:** 2 · **read:** 2 passage(s), 835 chars · **gold pages:** p.3 · **cited:** p.2, p.3

**Gold passage reached the prompt:** 1/1 quotes

**Answer**

> Ants use a special sense called smell to find their way home or follow others. When an ant moves, it leaves a scent on the ground that other ants can detect. This allows them to follow the trail left behind by another ant. Sometimes, ants also mark their own area with urine so they know where they belong.
> 
> Imagine you are walking along a path and someone follows your footsteps with their nose. You would think they are trying to find something or stay safe from danger. In fact, dogs often do this too, marking the road with their scent to show their territory. This same way works for ants, helping them navigate through dark holes without getting lost.
> 
> The book does not explain how ants know exactly which smell belongs to their specific path, but it clearly shows that they rely on following other ants and marking areas to stay safe.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| Ants use a special sense called smell to find their way home or follow others. | supported | He found out that as the ants move, they leave a smell on the ground. The other ants follow the smell to find the way. |
| When an ant moves, it leaves a scent on the ground that other ants can detect. | supported | He found out that as the ants move, they leave a smell on the ground. The other ants follow the smell to find the way. |
| This allows them to follow the trail left behind by another ant. | supported | He found out that as the ants move, they leave a smell on the ground. The other ants follow the smell to find the way. |
| Sometimes, ants also mark their own area with urine so they know where they belong. | **unsupported** | Dogs mark out their own area on the road. They can make out if another dog has come into their area by the smell of its urine or potty (latrine). |
| You would think they are trying to find something or stay safe from danger. | supported | He found out that as the ants move, they leave a smell on the ground. The other ants follow the smell to find the way. |
| In fact, dogs often do this too, marking the road with their scent to show their territory. | supported | Dogs mark out their own area on the road. They can make out if another dog has come into their area by the smell of its urine or potty (latrine). |
| This same way works for ants, helping them navigate through dark holes without getting lost. | supported | He found out that as the ants move, they leave a smell on the ground. The other ants follow the smell to find the way. |
| The book does not explain how ants know exactly which smell belongs to their specific path, but it clearly shows that they rely on following other ants and marking areas to stay safe. | supported | He found out that as the ants move, they leave a smell on the ground. The other ants follow the smell to find the way. |

*Not scored (1 sentence(s) asserting nothing):* invitation — Imagine you are walking along a path and someone follows your footsteps with their nose.

**What the book answers with:** ✓ ants leave a smell on the ground · ✗ other ants follow that smell

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 5 EVS (Looking Around) - pp. 3-4
… He found out that as the ants move, they leave a smell on the ground. The other ants follow the smell to find the way. Now carefully, without harming the ants, block their path for a while with a pencil. /rhombus4Now observe, how do the ants move? /rhombus4Have you seen a dog snif fing here and there? What do you think it is trying to smell? Dogs mark out their own area on the road. They can make out if another dog has come into their area by the smell of its urine or potty (latrine). /rhombus4Do you and your friends have similar answers? …

[2] NCERT Class 5 EVS (Looking Around) - p. 2
An ant was going along on the ground. It saw a group of ants coming from the other side. The first ant quickly came back to its hole. The ant guarding the hole recognised it and let it in. …
```
</details>

---

### `M2-herbivores` — What are herbivores and carnivores?

**Retrieved:** 2 · **read:** 2 passage(s), 861 chars · **gold pages:** p.6 · **cited:** p.5, p.6

**Gold passage reached the prompt:** 2/3 quotes

**Answer**

> Herbivores are animals that eat only plants or plant products, while carnivores are animals that eat only other animals. You can find these groups listed in the textbook by looking at Table 1.5 to see which creatures belong together. For example, cows are herbivores because they feed on grass, and lions are carnivores because they hunt down prey like zebras. Some animals eat both plants and meat, so you might need to look for a separate table that lists them in three different columns.
> 
> Think about why an animal eats only one type of food versus another, as the book suggests this information is important to understand how our food sources work.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| Herbivores are animals that eat only plants or plant products, while carnivores are animals that eat only other animals. | **CONTRADICTED** | known error: p.6 says herbivores eat only plants |
| You can find these groups listed in the textbook by looking at Table 1.5 to see which creatures belong together. | supported | Animals which eat only plants are called herbivores. |
| For example, cows are herbivores because they feed on grass, and lions are carnivores because they hunt down prey like zebras. | supported | Animals which eat only plants are called herbivores. |
| Some animals eat both plants and meat, so you might need to look for a separate table that lists them in three different columns. | supported | Animals which eat only plants are called herbivores. /square6Animals which eat only animals are called carnivores. … |

*Not scored (1 sentence(s) asserting nothing):* invitation — Think about why an animal eats only one type of food versus another, as the book suggests this information is important to understand how our food sources work.

**What the book answers with:** ✓ herbivores eat only plants · ✗ carnivores eat only animals

**Known error fired:** p.6 says herbivores eat only plants

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 6 Science - PRODUCTS AS FOOD - p. 5
… For some of them, the type of food they eat is also given. Fill in the blanks in the table. Have a look again at Table 1.5 and group the animals entered here as follows. Place animals which eat only plants or plant products in Group 1. These are called herbivores . There are some animals which eat other animals. Place these in Group 2. These animals are called carnivores . Do you find some animals which eat both plants and animals? Place them in Group 3. These are called omnivores. Prepare a table as in Table 1.6 and enter these separately in the three columns, as shown.

[2] NCERT Class 6 Science - Hs Cs - p. 6
… /square6The main sources of our food are plants and animals. /square6Animals which eat only plants are called herbivores. /square6Animals which eat only animals are called carnivores. …
```
</details>

---

### `M3-nutrients` — What are nutrients?

**Retrieved:** 2 · **read:** 2 passage(s), 860 chars · **gold pages:** p.8 · **cited:** p.8, p.16

**Gold passage reached the prompt:** 0/1 quotes

**Answer**

> Nutrients are the essential building blocks found in food that help keep your body healthy and strong. According to the textbook, these important components include carbohydrates, proteins, fats, vitamins, minerals, dietary fibres, and water. These ingredients provide energy for your daily activities or support growth and maintenance of your body. Vitamins specifically play a special role by helping protect you from getting sick. Without these nutrients, your body cannot function properly.
> 
> Think about how you need milk to grow taller when you are young; that is because proteins and minerals in the milk help build your bones. If you eat only bread without any other food, you might feel weak or tired because your body lacks the necessary building materials. The book explains that if your diet does not contain enough of these specific components, it can lead to a condition called a deficiency disease.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| Nutrients are the essential building blocks found in food that help keep your body healthy and strong. | supported | The major nutrients in our food are carbohydrates, proteins, fats, vitamins and minerals. |
| According to the textbook, these important components include carbohydrates, proteins, fats, vitamins, minerals, dietary fibres, and water. | supported | The major nutrients in our food are carbohydrates, proteins, fats, vitamins and minerals. In addition, food also contains dietary fibres and water. |
| These ingredients provide energy for your daily activities or support growth and maintenance of your body. | supported | Carbohydrates and fats mainly provide energy to our body. /square6 /square6/square6 /square6/square6Proteins and minerals are needed for the growth and the maintenance of our body. |
| Vitamins specifically play a special role by helping protect you from getting sick. | supported | Vitamins help in protecting our body against diseases. |
| Without these nutrients, your body cannot function properly. | supported | Proteins and minerals are needed for the growth and the maintenance of our body. |
| If you eat only bread without any other food, you might feel weak or tired because your body lacks the necessary building materials. | supported | Proteins and minerals are needed for the growth and the maintenance of our body. |
| The book explains that if your diet does not contain enough of these specific components, it can lead to a condition called a deficiency disease. | supported | Vitamins help in protecting our body against diseases. |

*Not scored (1 sentence(s) asserting nothing):* invitation — Think about how you need milk to grow taller when you are young; that is because proteins and minerals in the milk help build your bones.

**What the book answers with:** ✓ the major nutrients are carbohydrates, proteins, fats, vitamins and minerals

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 6 Science - DEFICIENCY DISEASES - p. 16
1 Vy , Vs , , /square6 /square6/square6 /square6/square6The major nutrients in our food are carbohydrates, proteins, fats, vitamins and minerals. In addition, food also contains dietary fibres and water. /square6 /square6/square6/square6/square6Carbohydrates and fats mainly provide energy to our body. /square6 /square6/square6 /square6/square6Proteins and minerals are needed for the growth and the maintenance of our body. /square6 /square6/square6 /square6/square6Vitamins help in protecting our body against diseases. …

[2] NCERT Class 6 Science - Hs Cs - pp. 8-9
… It may also include items like ingredients contain some components that are needed by our body. These components are called nutrients. The major nutrients in our food are named carbohydrates, proteins, fats, vitamins and minerals. …
```
</details>

---

### `M4-crop` — What is a crop?

**Retrieved:** 2 · **read:** 2 passage(s), 801 chars · **gold pages:** p.1 · **cited:** p.1, p.2

**Gold passage reached the prompt:** 1/1 quotes

**Answer**

> A crop is simply the name given to all plants grown at one place on a large scale for farming purposes. You already know that there are many different types of crops, such as cereals like wheat or vegetables, and fruits. These plants can be easily classified based on when they grow because their seasons change depending on where you live in India. Since the climate varies from region to region, farmers must choose specific crops that match the local temperature, humidity, and rainfall conditions. All living organisms need food to survive, and since plants are able to make their own food using sunlight, water, and soil nutrients, they become essential for feeding people and animals.
> 
> **Example:** If you plant wheat seeds in a field during the rainy season, those specific plants will grow into crops of wheat because the local conditions support them. However, if you try to grow vegetables in a hot desert region where there is no rain, those vegetables will likely fail to grow because the environment does not provide the necessary water for their survival.
> 
> Think further: How would you decide which type of food crop to plant next year based on the weather forecast?

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| A crop is simply the name given to all plants grown at one place on a large scale for farming purposes. | supported | When plants of the same kind are cultivated at one place on a large scale, it is called a crop. For example, crop of wheat means that all the plants grown in a field are that of wh |
| You already know that there are many different types of crops, such as cereals like wheat or vegetables, and fruits. | supported | When plants of the same kind are cultivated at one place on a large scale, it is called a crop. For example, crop of wheat means that all the plants grown in a field are that of wh |
| These plants can be easily classified based on when they grow because their seasons change depending on where you live in India. | supported | These can be classified on the basis of the season in which they grow. |
| Since the climate varies from region to region, farmers must choose specific crops that match the local temperature, humidity, and rainfall conditions. | supported | India is a vast country. The climatic conditions like temperature, humidity and rainfall vary from one region to another. |
| All living organisms need food to survive, and since plants are able to make their own food using sunlight, water, and soil nutrients, they become essential for feeding people and animals. | supported | When plants of the same kind are cultivated at one place on a large scale, it is called a crop. For example, crop of wheat means that all the plants grown in a field are that of wh |
| **Example:** If you plant wheat seeds in a field during the rainy season, those specific plants will grow into crops of wheat because the local conditions support them. | supported | When plants of the same kind are cultivated at one place on a large scale, it is called a crop. For example, crop of wheat means that all the plants grown in a field are that of wh |
| However, if you try to grow vegetables in a hot desert region where there is no rain, those vegetables will likely fail to grow because the environment does not provide the necessary water for their survival. | **CONTRADICTED** | — |

*Not scored (1 sentence(s) asserting nothing):* question — Think further: How would you decide which type of food crop to plant next year based on the weather forecast?

**What the book answers with:** ✗ a crop is plants of the same kind grown at one place on a large scale · ✓ grown on a large scale

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 8 Science - Agricultural Practices - p. 1
When plants of the same kind are cultivated at one place on a large scale, it is called a crop. For example, crop of wheat means that all the plants grown in a field are that of wheat. You already know that crops are of different types like cereals, vegetables and fruits. These can be classified on the basis of the season in which they grow. India is a vast country. The climatic conditions like temperature, humidity and rainfall vary from one region to another. Accordingly, there is a rich You have learnt that all living organisms require food. Plants can make their food themselves. …

[2] NCERT Class 8 Science - Preparation of Soil - p. 2
Cultivation of crops involves several activities undertaken by farmers over a period of time. …
```
</details>

---

### `M5-kharif-rabi` — What is the difference between kharif and rabi crops?

**Retrieved:** 2 · **read:** 2 passage(s), 900 chars · **gold pages:** p.2 · **cited:** p.2, p.15

**Gold passage reached the prompt:** 2/2 quotes

**Answer**

> Kharif crops are those grown during the rainy season, which usually occurs from June to September in India. This includes important plants like paddy, maize, soyabean, groundnut, and cotton. On the other hand, Rabi crops are specifically cultivated during the winter months between October and March. Common examples of these winter crops include wheat, gram, pea, mustard, and linseed. The main difference lies in the time of year when each type is planted: kharif crops follow the monsoon rains while rabi crops take advantage of cooler winter conditions.
> 
> Think about how your school schedule changes depending on whether it is raining outside or if the weather is cold enough to keep you indoors, just as farmers choose different crops based on seasonal weather patterns.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| Kharif crops are those grown during the rainy season, which usually occurs from June to September in India. | supported | Kharif Crops : The crops which are sown in the rainy season are called kharif crops. The rainy season in India is generally from June to September . |
| This includes important plants like paddy, maize, soyabean, groundnut, and cotton. | supported | (i) Kharif Crops : The crops which are sown in the rainy season are called kharif crops. The rainy season in India is generally from June to September . Paddy, maize, soyabean, gro |
| On the other hand, Rabi crops are specifically cultivated during the winter months between October and March. | supported | The crops grown in the winter season (October to March) are called rabi crops. |
| Common examples of these winter crops include wheat, gram, pea, mustard, and linseed. | supported | The crops grown in the winter season (October to March) are called rabi crops. Examples of rabi crops are wheat, gram, pea, mustard and linseed.” } 2 yes 2 yes 2 yes 2 yes 2 yes 2  |
| The main difference lies in the time of year when each type is planted: kharif crops follow the monsoon rains while rabi crops take advantage of cooler winter conditions. | supported | The rainy season in India is generally from June to September . |

*Not scored (1 sentence(s) asserting nothing):* invitation — Think about how your school schedule changes depending on whether it is raining outside or if the weather is cold enough to keep you indoors, just as farmers choose different crops based on seasonal weather patterns.

**What the book answers with:** ✓ kharif crops are sown in the rainy season · ✓ rabi crops are grown in the winter season

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 8 Science - Agricultural Practices - p. 2
(i) Kharif Crops : The crops which are sown in the rainy season are called kharif crops. The rainy season in India is generally from June to September .

Paddy, maize, soyabean, groundnut and cotton are kharif crops.

(ii) Rabi Crops : The crops grown in the winter season (October to March) are called rabi crops. Examples of rabi crops are wheat, gram, pea, mustard and linseed.

Besides these, pulses and vegetables are grown during summer at many places.

[2] NCERT Class 8 Science - WINNOWING - p. 15
… 4. A rabi crop that is also one of the pulses. 6. A process of separating the grain from chaff. 1. Sow some seeds in the soil and arrange to water them by drip irrigation. Observe daily. 2. Collect different types of seeds and put them in small bags. 3. Collect pictures of some other agricultural machines and paste them in a file. …
```
</details>

---

### `M6-tilling` — What is tilling?

**Retrieved:** 2 · **read:** 2 passage(s), 904 chars · **gold pages:** p.3 · **cited:** p.3

**Gold passage reached the prompt:** 1/1 quotes

**Answer**

> Tilling is the process of loosening and turning over the soil using a plough or hoe. This action breaks up large clumps of dirt called crumbs so that crops can grow better. It also helps to mix manure into the ground before planting. Levelling the field afterward ensures that water and seeds spread evenly across the land. Without this preparation, many crops would not survive due to poor soil structure.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| Tilling is the process of loosening and turning over the soil using a plough or hoe. | supported | turning and loosening of soil is very important for cultivation of crops. The process of loosening and turning of the soil is called tilling or ploughing. This is done by using a p |
| This action breaks up large clumps of dirt called crumbs so that crops can grow better. | supported | It is necessary to break these crumbs. |
| It also helps to mix manure into the ground before planting. | supported | Sometimes, manure is added to the soil before tilling. |
| Levelling the field afterward ensures that water and seeds spread evenly across the land. | supported | Levelling the field is beneficial for sowing as well as for irrigation. |
| Without this preparation, many crops would not survive due to poor soil structure. | supported | turning and loosening of soil is very important for cultivation of crops. |

**What the book answers with:** ✓ tilling is loosening and turning the soil

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 8 Science - Preparation of Soil - p. 3
turning and loosening of soil is very important for cultivation of crops. The process of loosening and turning of the soil is called tilling or ploughing. This is done by using a plough. Ploughs are made of wood or iron. If the soil is very dry, it may need watering before ploughing. The ploughed field may have big clumps of soil called crumbs. It is necessary to break these crumbs. Levelling the field is beneficial for sowing as well as for irrigation. Levelling of soil is done with the help of a leveller. Sometimes, manure is added to the soil before tilling. …

[2] NCERT Class 8 Science - Agricultural Implements - p. 3
… The main tools used for this purpose are the plough, hoe and cultivator. Plough : This is being used since ancient times for tilling the soil, adding fertilisers to the crop, removing the weeds and turning the soil. …
```
</details>

---

### `M7-density` — What is density?

**Retrieved:** 2 · **read:** 2 passage(s), 688 chars · **gold pages:** p.6 · **cited:** p.142

**Gold passage reached the prompt:** 0/1 quotes

**Answer**

> Density is defined as the mass of a specific amount of space or unit volume, which is a fundamental characteristic property of every material found in nature. This means that if you take any sample of a substance and measure its mass while keeping the volume constant, the density will always stay the same for that exact type of material under those conditions. Because different materials have different amounts of matter packed into the same space, their densities are also completely different from one another. For instance, gold has a very high density of 19300 kilograms per cubic meter, while water has a much lower density of only 1000 kilograms per cubic meter. This difference in density allows scientists to determine if an object is pure or mixed with other materials by comparing its actual density to known values for specific substances.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| Density is defined as the mass of a specific amount of space or unit volume, which is a fundamental characteristic property of every material found in nature. | supported | As you know, the density of a substance is defined as mass of a unit volume. |
| This means that if you take any sample of a substance and measure its mass while keeping the volume constant, the density will always stay the same for that exact type of material under those conditions. | supported | The density of a given substance, under specified conditions, remains the same. |
| Because different materials have different amounts of matter packed into the same space, their densities are also completely different from one another. | supported | As you know, the density of a substance is defined as mass of a unit volume. |
| For instance, gold has a very high density of 19300 kilograms per cubic meter, while water has a much lower density of only 1000 kilograms per cubic meter. | supported | The density of gold is 19300 kg m-3 while that of water is 1000 kg m-3. |
| This difference in density allows scientists to determine if an object is pure or mixed with other materials by comparing its actual density to known values for specific substances. | supported | The density of a given sample of a substance can help us to determine its purity. |

**What the book answers with:** ✓ density is mass per unit volume

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 9 Science - 2BUOYANCY - p. 142
As you know, the density of a substance is defined as mass of a unit volume. The unit of density is kilogram per metre cube (kg m-3). The density of a given substance, under specified conditions, remains the same. Therefore the density of a substance is one of its characteristic properties. It is different for different substances. For example, the density of gold is 19300 kg m-3 while that of water is 1000 kg m-3. The density of a given sample of a substance can help us to determine its purity.

[2] NCERT Class 9 Science - 2BUOYANCY - p. 142
It is often convenient to express density of a substance in comparison with that of water. …
```
</details>

---

### `M8-melting-point` — What is the melting point of a solid?

**Retrieved:** 1 · **read:** 1 passage(s), 598 chars · **gold pages:** p.7 · **cited:** p.7

**Gold passage reached the prompt:** 2/2 quotes

**Answer**

> A melting point is the specific temperature at which a solid turns completely into a liquid under normal conditions. This happens when enough heat energy breaks the strong forces holding the particles together in the solid state. The book explains that this temperature indicates how tightly the particles are attracted to each other, so higher melting points mean stronger attractions. For example, ice melts at 273.15 K because its particles need just enough heat to overcome these bonds. When a solid melts, its temperature stays constant while it changes state, which is why you can see the heat energy being used to break bonds rather than raise the temperature.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| A melting point is the specific temperature at which a solid turns completely into a liquid under normal conditions. | supported | The minimum temperature at which a solid melts to become a liquid at the atmospheric pressure is called its melting point. |
| This happens when enough heat energy breaks the strong forces holding the particles together in the solid state. | supported | The melting point of a solid is an indication of the strength of the force of attraction between its particles. |
| The book explains that this temperature indicates how tightly the particles are attracted to each other, so higher melting points mean stronger attractions. | supported | The melting point of a solid is an indication of the strength of the force of attraction between its particles. |
| For example, ice melts at 273.15 K because its particles need just enough heat to overcome these bonds. | supported | The melting point of ice is 273.15 K |
| When a solid melts, its temperature stays constant while it changes state, which is why you can see the heat energy being used to break bonds rather than raise the temperature. | supported | When a solid melts, its temperature remains the same, so where does the heat energy go? |

**What the book answers with:** ✓ the melting point is the minimum temperature at which a solid becomes a liquid

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 9 Science - EFFECT OF CHANGE OF TEMPERATURE - p. 7
… A stage is reached when the solid melts and is converted to a liquid. The minimum temperature at which a solid melts to become a liquid at the atmospheric pressure is called its melting point. The melting point of a solid is an indication of the strength of the force of attraction between its particles. The melting point of ice is 273.15 K*. The process of melting, that is, change of solid state into liquid state is also known as fusion. When a solid melts, its temperature remains the same, so where does the heat energy go?
```
</details>

---

### `M9-combination` — What is a combination reaction?

**Retrieved:** 2 · **read:** 2 passage(s), 866 chars · **gold pages:** p.6 · **cited:** p.6, p.14

**Gold passage reached the prompt:** 2/2 quotes

**Answer**

> A combination reaction occurs when two or more separate substances join together to create a single new product. This type of chemical process follows the rule that reactants combine directly without breaking down into smaller parts, resulting in one final substance. For instance, when quick lime reacts with water, calcium oxide combines with water molecules to form slaked lime, which is a classic example of this reaction. You can picture this like mixing two different ingredients in a bowl until they merge completely into one uniform mixture. However, if you look at the specific textbook excerpt provided for this topic, it does not explain how or why this particular chemical change happens, so we must rely on the general definition given here instead.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| A combination reaction occurs when two or more separate substances join together to create a single new product. | supported | In a combination reaction two or more substances combine to form a new single substance. |
| This type of chemical process follows the rule that reactants combine directly without breaking down into smaller parts, resulting in one final substance. | supported | In a combination reaction two or more substances combine to form a new single substance. |
| For instance, when quick lime reacts with water, calcium oxide combines with water molecules to form slaked lime, which is a classic example of this reaction. | supported | In a combination reaction two or more substances combine to form a new single substance. |
| You can picture this like mixing two different ingredients in a bowl until they merge completely into one uniform mixture. | supported | In a combination reaction two or more substances combine to form a new single substance. |
| However, if you look at the specific textbook excerpt provided for this topic, it does not explain how or why this particular chemical change happens, so we must rely on the general definition given here instead. | supported | In a combination reaction two or more substances combine to form a new single substance. |

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

[2] NCERT Class 10 Science - Rancidity - p. 14
… Equations must always be balanced. /square6In a combination reaction two or more substances combine to form a new single substance. /square6Decomposition reactions are opposite to combination reactions. …
```
</details>

---

### `M10-exothermic` — What is an exothermic reaction?

**Retrieved:** 2 · **read:** 2 passage(s), 879 chars · **gold pages:** p.7 · **cited:** p.7, p.14

**Gold passage reached the prompt:** 1/1 quotes

**Answer**

> An exothermic reaction is a chemical process where energy, usually in the form of heat, is released into the surroundings during the formation of products. This happens because the bonds formed between new atoms release more energy than was required to break the initial bonds, causing the system to warm up. According to the textbook excerpt provided, this specific type of reaction is defined by the fact that it evolves a large amount of heat along with the creation of new substances. A common everyday example given in the text is the burning of natural gas, which warms the room as it burns completely. Students should remember that if you cannot find an explanation or example in your book, you must simply state that the material does not cover that specific detail instead of guessing facts yourself.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| An exothermic reaction is a chemical process where energy, usually in the form of heat, is released into the surroundings during the formation of products. | supported | In Activity 1.4, we also observed that a large amount of heat is evolved. This makes the reaction mixture warm. Reactions in which heat is released along with the formation of prod |
| This happens because the bonds formed between new atoms release more energy than was required to break the initial bonds, causing the system to warm up. | **unsupported** | In Activity 1.4, we also observed that a large amount of heat is evolved. This makes the reaction mixture warm. Reactions in which heat is released along with the formation of prod |
| According to the textbook excerpt provided, this specific type of reaction is defined by the fact that it evolves a large amount of heat along with the creation of new substances. | supported | In Activity 1.4, we also observed that a large amount of heat is evolved. This makes the reaction mixture warm. Reactions in which heat is released along with the formation of prod |
| A common everyday example given in the text is the burning of natural gas, which warms the room as it burns completely. | supported | In Activity 1.4, we also observed that a large amount of heat is evolved. This makes the reaction mixture warm. |
| Students should remember that if you cannot find an explanation or example in your book, you must simply state that the material does not cover that specific detail instead of guessing facts yourself. | **CONTRADICTED** | Reactions in which energy is absorbed are known as endothermic reactions. |

**What the book answers with:** ✗ heat is released

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 10 Science - CTIONSCTIONS - p. 7
In Activity 1.4, we also observed that a large amount of heat is evolved. This makes the reaction mixture warm. Reactions in which heat is released along with the formation of products are called exothermic chemical reactions.

Other examples of exothermic reactions are -

(i) Burning of natural gas

[2] NCERT Class 10 Science - Rancidity - p. 14
/square6Reactions in which energy is absorbed are known as endothermic reactions. /square6When an element displaces another element from its compound, a displacement reaction occurs. /square6Two different atoms or groups of atoms (ions) are exchanged in double displacement reactions. /square6Precipitation reactions produce insoluble salts. /square6Reactions also involve the gain or loss of oxygen or hydrogen by substances. Oxidation is the gain of oxygen or loss of hydrogen. …
```
</details>

---

### `M11-displacement` — What is a displacement reaction?

**Retrieved:** 2 · **read:** 2 passage(s), 886 chars · **gold pages:** p.11 · **cited:** p.11, p.14

**Gold passage reached the prompt:** 1/1 quotes

**Answer**

> A displacement reaction occurs when one element replaces another element within a compound, causing them to swap places. This happens because the new element is either more or less reactive than the original one present in the mixture. For instance, if you mix iron filings with copper sulphate solution, the iron will take over and remove copper from the liquid, leaving behind reddish-brown iron oxide powder while the blue colour fades away.
> 
> This specific process is often written as a chemical equation where two different atoms or groups of atoms exchange their positions to form new substances. The book provides a clear example showing how iron displaces copper from its compound, resulting in the formation of aluminium oxide and iron metal. You can picture this as a tug-of-war game where one stronger player forces the weaker player out of their position on the ground.
> 
> It is important to note that not every reaction involving swapping elements counts as a displacement; only those driven by specific reactivity rules apply. If you are unsure whether a particular reaction fits this pattern, please check your textbook for the exact conditions required for such a swap to occur.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| A displacement reaction occurs when one element replaces another element within a compound, causing them to swap places. | supported | When an element displaces another element from its compound, a displacement reaction occurs. |
| This happens because the new element is either more or less reactive than the original one present in the mixture. | supported | When an element displaces another element from its compound, a displacement reaction occurs. |
| For instance, if you mix iron filings with copper sulphate solution, the iron will take over and remove copper from the liquid, leaving behind reddish-brown iron oxide powder while the blue colour fades away. | supported | In this reaction, iron has displaced or removed another element, copper, from copper sulphate solution. This reaction is known as displacement reaction. |
| This specific process is often written as a chemical equation where two different atoms or groups of atoms exchange their positions to form new substances. | supported | /square6Two different atoms or groups of atoms (ions) are exchanged in double displacement reactions. |
| The book provides a clear example showing how iron displaces copper from its compound, resulting in the formation of aluminium oxide and iron metal. | supported | Fe2O3 + 2Al → Al2O3 + 2Fe |
| You can picture this as a tug-of-war game where one stronger player forces the weaker player out of their position on the ground. | **unsupported** | — |
| It is important to note that not every reaction involving swapping elements counts as a displacement; only those driven by specific reactivity rules apply. | supported | When an element displaces another element from its compound, a displacement reaction occurs. |
| If you are unsure whether a particular reaction fits this pattern, please check your textbook for the exact conditions required for such a swap to occur. | supported | When an element displaces another element from its compound, a displacement reaction occurs. |

**What the book answers with:** ✓ one element displaces another from its compound

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 10 Science - Rancidity - p. 14
/square6Reactions in which energy is absorbed are known as endothermic reactions. /square6When an element displaces another element from its compound, a displacement reaction occurs.

/square6Two different atoms or groups of atoms (ions) are exchanged in double displacement reactions.

/square6Precipitation reactions produce insoluble salts.

/square6Reactions also involve the gain or loss of oxygen or hydrogen by substances. Oxidation is the gain of oxygen or loss of hydrogen. Reduction is the loss of oxygen or gain of hydrogen.

2. Fe2O3 + 2Al → Al2O3 + 2Fe

[2] NCERT Class 10 Science - Decomposition Reaction - pp. 11-12
In this reaction, iron has displaced or removed another element, copper, from copper sulphate solution. This reaction is known as displacement reaction. Zinc and lead are more reactive elements than copper. …
```
</details>

---

### `M12-participial` — What is a participial phrase?

**Retrieved:** 2 · **read:** 2 passage(s), 846 chars · **gold pages:** p.52 · **cited:** p.52, p.77

**Gold passage reached the prompt:** 1/1 quotes

**Answer**

> A participial phrase is a group of words that begins with an -ing verb and describes something happening while another part of the sentence is taking place. These phrases add extra meaning to the main idea by showing how one action affects another person or thing. For instance, if you say "The boy was chased by the dog," the phrase "chased by the dog" explains that the chase happened simultaneously with the state of being chased. This structure helps writers show relationships between actions without needing to name every single actor involved in the story. Students should remember that these phrases are often used to focus attention on what is happening rather than who is doing it, making sentences more vivid and interesting.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| A participial phrase is a group of words that begins with an -ing verb and describes something happening while another part of the sentence is taking place. | supported | Participial phrases say something more about the person or thing talked about or the idea expressed by the sentence as a whole. |
| These phrases add extra meaning to the main idea by showing how one action affects another person or thing. | **CONTRADICTED** | Participial phrases say something more about the person or thing talked about or the idea expressed by the sentence as a whole. |
| For instance, if you say "The boy was chased by the dog," the phrase "chased by the dog" explains that the chase happened simultaneously with the state of being chased. | **unsupported** | Einstein became a gifted amateur violinist. He maintained this skill throughout his life. |
| This structure helps writers show relationships between actions without needing to name every single actor involved in the story. | supported | The italicised verbs in these sentences are made up of a form of the verb be and a past participle. (For example: were + regarded, was + asked, be + confronted) These sentences foc |
| Students should remember that these phrases are often used to focus attention on what is happening rather than who is doing it, making sentences more vivid and interesting. | supported | The italicised verbs in these sentences are made up of a form of the verb be and a past participle. (For example: were + regarded, was + asked, be + confronted) These sentences foc |

**What the book answers with:** ✓ a participial phrase begins with an -ing verb

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 9 English (Beehive) - / Beehive - p. 52
• Letters survive in which they put their affection into words, mixing science with tenderness.

The parts in italics in the above sentences begin with -ing verbs, and are called participial phrases. Participial phrases say something more about the person or thing talked about or the idea expressed by the sentence as a whole. For example:

- Einstein became a gifted amateur violinist. He maintained this skill throughout his life.

[2] NCERT Class 9 English (Beehive) - / Beehive - p. 77
The italicised verbs in these sentences are made up of a form of the verb be and a past participle. (For example: were + regarded, was + asked, be + confronted) These sentences focus on what happens , rather than who does what . Notice that the doer of the action is not included in the sentences. …
```
</details>

---

### `M13-crop-classified` — How are they classified?

*Asked after* “What is a crop?” *in the same session — the pronoun only resolves because that turn happened.*

**Retrieved:** 2 · **read:** 2 passage(s), 902 chars · **gold pages:** p.1, p.2 · **cited:** p.1, p.15

**Gold passage reached the prompt:** 1/2 quotes

**Answer**

> A crop refers to plants of the same kind grown on a large scale at one place. You already know that crops can be classified based on the season in which they grow. For instance, you have learned that all living organisms require food and that plants can make their own food using sunlight. This means wheat is just one type of crop that grows during specific seasons like summer or winter. The book explains that these different types are grouped together according to whether they bloom in spring or autumn. You might picture a farmer planting rice in the rainy season while another farmer grows corn in the dry season to show this difference clearly.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| A crop refers to plants of the same kind grown on a large scale at one place. | supported | When plants of the same kind are cultivated at one place on a large scale, it is called a crop. For example, crop of wheat means that all the plants grown in a field are that of wh |
| You already know that crops can be classified based on the season in which they grow. | supported | These can be classified on the basis of the season in which they grow. |
| For instance, you have learned that all living organisms require food and that plants can make their own food using sunlight. | supported | When plants of the same kind are cultivated at one place on a large scale, it is called a crop. |
| This means wheat is just one type of crop that grows during specific seasons like summer or winter. | supported | When plants of the same kind are cultivated at one place on a large scale, it is called a crop. For example, crop of wheat means that all the plants grown in a field are that of wh |
| The book explains that these different types are grouped together according to whether they bloom in spring or autumn. | supported | These can be classified on the basis of the season in which they grow. |
| You might picture a farmer planting rice in the rainy season while another farmer grows corn in the dry season to show this difference clearly. | supported | 5. Certain plants of the same kind grown on a large scale. |

**What the book answers with:** ✓ crops are classified by the season in which they grow

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 8 Science - Agricultural Practices - p. 1
When plants of the same kind are cultivated at one place on a large scale, it is called a crop. For example, crop of wheat means that all the plants grown in a field are that of wheat. You already know that crops are of different types like cereals, vegetables and fruits. These can be classified on the basis of the season in which they grow. India is a vast country. The climatic conditions like temperature, humidity and rainfall vary from one region to another. Accordingly, there is a rich You have learnt that all living organisms require food. Plants can make their food themselves. …

[2] NCERT Class 8 Science - WINNOWING - p. 15
1. Providing water to the crops. 2. Keeping crop grains for a long time under proper conditions. 5. Certain plants of the same kind grown on a large scale. 3. A machine used for cutting the matured crop. …
```
</details>

---

### `M14-exothermic-example` — Can you give me an example of one?

*Asked after* “What is an exothermic reaction?” *in the same session — the pronoun only resolves because that turn happened.*

**Retrieved:** 2 · **read:** 2 passage(s), 871 chars · **gold pages:** p.7 · **cited:** p.7

**Gold passage reached the prompt:** 1/1 quotes

**Answer**

> An exothermic reaction is a chemical process where heat energy is released and given out as a byproduct along with the formation of new products. This happens because the bonds formed in the final product are stronger than the initial bonds broken during the reaction, causing the excess energy to leave the system. A common everyday example of this is burning natural gas, which produces warmth while creating carbon dioxide and water vapor.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| An exothermic reaction is a chemical process where heat energy is released and given out as a byproduct along with the formation of new products. | supported | In Activity 1.4, we also observed that a large amount of heat is evolved. This makes the reaction mixture warm. Reactions in which heat is released along with the formation of prod |
| This happens because the bonds formed in the final product are stronger than the initial bonds broken during the reaction, causing the excess energy to leave the system. | **unsupported** | In Activity 1.4, we also observed that a large amount of heat is evolved. This makes the reaction mixture warm. Reactions in which heat is released along with the formation of prod |
| A common everyday example of this is burning natural gas, which produces warmth while creating carbon dioxide and water vapor. | supported | Burning of natural gas |

**What the book answers with:** ✓ burning of natural gas is an example

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 10 Science - CTIONSCTIONS - p. 7
In Activity 1.4, we also observed that a large amount of heat is evolved. This makes the reaction mixture warm. Reactions in which heat is released along with the formation of products are called exothermic chemical reactions.

Other examples of exothermic reactions are -

(i) Burning of natural gas

[2] NCERT Class 10 Science - CTIONSCTIONS - p. 7
… These carbohydrates are broken down to form glucose. This glucose combines with oxygen in the cells of our body and provides energy. The special name of this reaction is respiration, the process of which you will study in Chapter 6. (iii) The decomposition of vegetable matter into compost is also an example of an exothermic reaction. Identify the type of the reaction taking place in Activity 1.1, where heat is given out along with the formation of a single product.
```
</details>

