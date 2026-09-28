# Groundedness run — pack-only

2026-09-28T10:23:13+00:00 · tutor `qwen3.5:2b-q4_K_M` · http://127.0.0.1:8756 · budget backend default · judge gemma3:4b (local, via Ollama)

Gold set `docs/groundedness/evalset-multibook.json` over *NCERT Class 5 EVS (Looking Around), NCERT Class 6 Science, NCERT Class 8 Science, NCERT Class 9 Science, NCERT Class 9 English (Beehive) and NCERT Class 10 Science*. Each answer is graded against the excerpt block that turn actually read, not against the pages it cited.

## Headline

| | |
|---|---|
| Groundedness (claims) | **86%** (62/72 claims supported) |
| Groundedness (per turn) | 83% |
| Contradictions | **3** claims, in 3 of 14 turns |
| Unsupported | 7 claims |
| Key coverage | 68% |
| Context recall | 80% of gold passages reached the prompt |
| Fully grounded turns | 7/14 |
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
| `M1-ant-smell` | 89% | 50% | 100% | 9 | grounded and complete |
| `M2-herbivores` | 67% | 0% | 67% | 3 | contradicts the book |
| `M3-nutrients` | 100% | 100% | 0% | 7 | grounded and complete |
| `M4-crop` | 80% | 100% | 100% | 5 | contradicts the book |
| `M5-kharif-rabi` | 100% | 100% | 100% | 5 | grounded and complete |
| `M6-tilling` | 100% | 100% | 100% | 4 | grounded and complete |
| `M7-density` | 100% | 100% | 0% | 5 | grounded and complete |
| `M8-melting-point` | 75% | 100% | 100% | 4 | right, but not from the book |
| `M9-combination` | 100% | 0% | 100% | 7 | grounded but thin |
| `M10-exothermic` | 50% | 0% | 100% | 4 | contradicts the book |
| `M11-displacement` | 100% | 100% | 100% | 6 | grounded and complete |
| `M12-participial` | 40% | 100% | 100% | 5 | right, but not from the book |
| `M13-crop-classified` | 100% | 0% | 50% | 5 | grounded but thin |
| `M14-exothermic-example` | 67% | 100% | 100% | 3 | right, but not from the book |

---

### `M1-ant-smell` — How do ants find their way?

**Retrieved:** 2 · **read:** 2 passage(s), 835 chars · **gold pages:** p.3 · **cited:** p.2, p.3

**Gold passage reached the prompt:** 1/1 quotes

**Answer**

> Ants use a special sense called pheromones to find their way home. When an ant moves, it leaves a faint smell on the ground behind its body. Other ants can smell this scent and follow the trail to reach their destination. This is how they know where to go without getting lost.
> 
> Imagine you are walking in a dark forest with no light around you. You might see a group of people coming from the other side, but you cannot see them clearly because it is dark. However, if one person starts walking and leaves a scent on the ground, others can easily follow that trail to find their way home. This same principle helps ants navigate through their environment just like you would use a scent trail in the dark.
> 
> Think about how dogs mark out their own area on the road by leaving a special smell from their urine or potty. They can make sure no other dog enters their territory by checking if another dog has come along. This is exactly how ants work to find their way back home!

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| Ants use a special sense called pheromones to find their way home. | supported | He found out that as the ants move, they leave a smell on the ground. The other ants follow the smell to find the way. |
| When an ant moves, it leaves a faint smell on the ground behind its body. | supported | He found out that as the ants move, they leave a smell on the ground. |
| Other ants can smell this scent and follow the trail to reach their destination. | supported | He found out that as the ants move, they leave a smell on the ground. The other ants follow the smell to find the way. |
| This is how they know where to go without getting lost. | supported | He found out that as the ants move, they leave a smell on the ground. The other ants follow the smell to find the way. |
| You might see a group of people coming from the other side, but you cannot see them clearly because it is dark. | **unsupported** | The ant guarding the hole recognised it and let it in. |
| However, if one person starts walking and leaves a scent on the ground, others can easily follow that trail to find their way home. | supported | He found out that as the ants move, they leave a smell on the ground. The other ants follow the smell to find the way. |
| This same principle helps ants navigate through their environment just like you would use a scent trail in the dark. | supported | He found out that as the ants move, they leave a smell on the ground. The other ants follow the smell to find the way. |
| They can make sure no other dog enters their territory by checking if another dog has come along. | supported | Dogs mark out their own area on the road. They can make out if another dog has come into their area by the smell of its urine or potty (latrine). |
| This is exactly how ants work to find their way back home! | supported | He found out that as the ants move, they leave a smell on the ground. The other ants follow the smell to find the way. |

*Not scored (2 sentence(s) asserting nothing):* invitation — Imagine you are walking in a dark forest with no light around you.; invitation — Think about how dogs mark out their own area on the road by leaving a special smell from their urine or potty.

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

> Herbivores are animals that feed exclusively on plants or plant products, while carnivores are animals that eat only other animals. Some creatures belong to both groups by eating both types of food. These classifications help scientists understand how different animals survive in nature.
> 
> Think about a cow eating grass versus a lion hunting a zebra; these examples show how the diet determines the animal's name.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| Herbivores are animals that feed exclusively on plants or plant products, while carnivores are animals that eat only other animals. | **CONTRADICTED** | known error: p.6 says herbivores eat only plants |
| Some creatures belong to both groups by eating both types of food. | supported | Animals which eat both plants and animals? Place them in Group 3. These are called omnivores. |
| These classifications help scientists understand how different animals survive in nature. | supported | Animals which eat only plants are called herbivores. /square6Animals which eat only animals are called carnivores. … |

*Not scored (1 sentence(s) asserting nothing):* invitation — Think about a cow eating grass versus a lion hunting a zebra; these examples show how the diet determines the animal's name.

**What the book answers with:** ✗ herbivores eat only plants · ✗ carnivores eat only animals

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

> Nutrients are the essential substances found in food that provide energy and support the growth and maintenance of your body. These important components include carbohydrates, proteins, fats, vitamins, minerals, dietary fibres, and water. Your body needs these specific ingredients to function properly and stay healthy. For example, when you eat an apple, it provides nutrients like vitamins and fibre that help protect your body against diseases.
> 
> Think about how a car engine works; without oil or fuel, the machine cannot run. Similarly, your body cannot work without its specific nutrients. Why are these particular ingredients so important? Because they contain the exact components needed by our cells to perform daily tasks. Without them, you would feel weak and sick.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| Nutrients are the essential substances found in food that provide energy and support the growth and maintenance of your body. | supported | The major nutrients in our food are carbohydrates, proteins, fats, vitamins and minerals. |
| These important components include carbohydrates, proteins, fats, vitamins, minerals, dietary fibres, and water. | supported | The major nutrients in our food are carbohydrates, proteins, fats, vitamins and minerals. In addition, food also contains dietary fibres and water. |
| Your body needs these specific ingredients to function properly and stay healthy. | supported | The major nutrients in our food are carbohydrates, proteins, fats, vitamins and minerals. |
| For example, when you eat an apple, it provides nutrients like vitamins and fibre that help protect your body against diseases. | supported | Vitamins help in protecting our body against diseases. |
| Similarly, your body cannot work without its specific nutrients. | supported | The major nutrients in our food are carbohydrates, proteins, fats, vitamins and minerals. |
| Because they contain the exact components needed by our cells to perform daily tasks. | supported | The major nutrients in our food are named carbohydrates, proteins, fats, vitamins and minerals. |
| Without them, you would feel weak and sick. | supported | Proteins and minerals are needed for the growth and the maintenance of our body. |

*Not scored (2 sentence(s) asserting nothing):* invitation — Think about how a car engine works; without oil or fuel, the machine cannot run.; question — Why are these particular ingredients so important?

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

> A crop is simply the name given to plants that are grown together in the same field on a large scale. You already know from your textbook that there are many different kinds of crops, such as cereals, vegetables, and fruits, which can be sorted by when they grow or what type of food they provide. Because India is so big, the weather changes from place to place, meaning farmers must choose specific plants for each region based on local conditions like temperature and rainfall. Plants need food to survive, and while some animals eat other living things, only plants can make their own food using sunlight. Therefore, when you hear the word crop, think of a large group of similar plants being grown together in one spot, just like how all the wheat plants in a field are considered the same kind of plant.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| A crop is simply the name given to plants that are grown together in the same field on a large scale. | supported | When plants of the same kind are cultivated at one place on a large scale, it is called a crop. For example, crop of wheat means that all the plants grown in a field are that of wh |
| You already know from your textbook that there are many different kinds of crops, such as cereals, vegetables, and fruits, which can be sorted by when they grow or what type of food they provide. | supported | When plants of the same kind are cultivated at one place on a large scale, it is called a crop. For example, crop of wheat means that all the plants grown in a field are that of wh |
| Because India is so big, the weather changes from place to place, meaning farmers must choose specific plants for each region based on local conditions like temperature and rainfall. | supported | India is a vast country. The climatic conditions like temperature, humidity and rainfall vary from one region to another. |
| Plants need food to survive, and while some animals eat other living things, only plants can make their own food using sunlight. | **CONTRADICTED** | Plants can make their food themselves. |
| Therefore, when you hear the word crop, think of a large group of similar plants being grown together in one spot, just like how all the wheat plants in a field are considered the same kind of plant. | supported | When plants of the same kind are cultivated at one place on a large scale, it is called a crop. For example, crop of wheat means that all the plants grown in a field are that of wh |

**What the book answers with:** ✓ a crop is plants of the same kind grown at one place on a large scale · ✓ grown on a large scale

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

> Kharif and rabi are two main categories of crops grown in India based on when they are planted during the year. Kharif crops are those sown in the rainy season, which typically runs from June to September, while Rabi crops are grown during the cooler winter months between October and March. The text lists specific examples for each group, such as paddy and maize being kharif crops, whereas wheat and gram belong to the rabi category. Beyond these primary groups, pulses and vegetables can also be cultivated in the summer at many places. Understanding this seasonal split helps students see how farmers choose which plants to grow depending on the weather conditions available each year.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| Kharif and rabi are two main categories of crops grown in India based on when they are planted during the year. | supported | Kharif Crops : The crops which are sown in the rainy season are called kharif crops. The rainy season in India is generally from June to September . Paddy, maize, soyabean, groundn |
| Kharif crops are those sown in the rainy season, which typically runs from June to September, while Rabi crops are grown during the cooler winter months between October and March. | supported | Kharif Crops : The crops which are sown in the rainy season are called kharif crops. The rainy season in India is generally from June to September .”, 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 |
| The text lists specific examples for each group, such as paddy and maize being kharif crops, whereas wheat and gram belong to the rabi category. | supported | Paddy, maize, soyabean, groundnut and cotton are kharif crops. Wheat, gram, pea, mustard and linseed are rabi crops. |
| Beyond these primary groups, pulses and vegetables can also be cultivated in the summer at many places. | supported | [2] NCERT Class 8 Science - WINNOWING - p. 15
… 4. A rabi crop that is also one of the pulses. 6. A process of separating the grain from chaff. 1. Sow some seeds in the soil and ar |
| Understanding this seasonal split helps students see how farmers choose which plants to grow depending on the weather conditions available each year. | supported | The crops which are sown in the rainy season are called kharif crops. The rainy season in India is generally from June to September . |

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

> Tilling is the process of loosening and turning over the soil using a tool called a plough. This action breaks up hard clumps of dirt into smaller pieces known as crumbs, which helps the soil mix better with water and air needed for plant growth. Farmers often add manure to the soil before starting this work to improve its quality. After tilling, the field is usually leveled using a special tool called a leveller so that seeds can be planted evenly.
> 
> Think about how you would prepare your garden bed by digging it up and mixing in some compost from your backyard.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| Tilling is the process of loosening and turning over the soil using a tool called a plough. | supported | turning and loosening of soil is very important for cultivation of crops. The process of loosening and turning of the soil is called tilling or ploughing. This is done by using a p |
| This action breaks up hard clumps of dirt into smaller pieces known as crumbs, which helps the soil mix better with water and air needed for plant growth. | supported | turning and loosening of soil is very important for cultivation of crops. The process of loosening and turning of the soil is called tilling or ploughing. This is done by using a p |
| Farmers often add manure to the soil before starting this work to improve its quality. | supported | Sometimes, manure is added to the soil before tilling. |
| After tilling, the field is usually leveled using a special tool called a leveller so that seeds can be planted evenly. | supported | Levelling the field is beneficial for sowing as well as for irrigation. |

*Not scored (1 sentence(s) asserting nothing):* invitation — Think about how you would prepare your garden bed by digging it up and mixing in some compost from your backyard.

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

> Density is defined as the mass of a specific amount of space, which means it tells you how heavy something feels for its size. This value stays constant for any given material under normal conditions, making it a key characteristic that helps scientists identify substances. For instance, gold has a very high density of 19300 kilograms per cubic meter because it is extremely heavy for its volume. In contrast, water has a much lower density of 1000 kilograms per cubic meter, which is why it floats on top of gold. By comparing the densities of different materials, you can easily determine if an object is pure or mixed with something else.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| Density is defined as the mass of a specific amount of space, which means it tells you how heavy something feels for its size. | supported | As you know, the density of a substance is defined as mass of a unit volume. |
| This value stays constant for any given material under normal conditions, making it a key characteristic that helps scientists identify substances. | supported | The density of a given substance, under specified conditions, remains the same. |
| For instance, gold has a very high density of 19300 kilograms per cubic meter because it is extremely heavy for its volume. | supported | The density of gold is 19300 kg m-3 |
| In contrast, water has a much lower density of 1000 kilograms per cubic meter, which is why it floats on top of gold. | supported | The density of a given substance, under specified conditions, remains the same. |
| By comparing the densities of different materials, you can easily determine if an object is pure or mixed with something else. | supported | The density of a given sample of a substance can help us to determine its purity. |

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

> A melting point is the specific temperature at which a solid turns completely into a liquid under normal atmospheric pressure. This happens when the particles in the solid gain enough energy to overcome the strong forces holding them together, allowing them to slide past one another like a crowd of people moving out of an elevator door. The heat energy absorbed by the solid does not raise its temperature during this phase change because it is used specifically to break these attractive bonds rather than increasing particle speed. For example, ice melts at 0 degrees Celsius, meaning that once the water reaches this exact temperature, any additional heat will simply turn the ice into liquid without changing the temperature reading.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| A melting point is the specific temperature at which a solid turns completely into a liquid under normal atmospheric pressure. | supported | The minimum temperature at which a solid melts to become a liquid at the atmospheric pressure is called its melting point. |
| This happens when the particles in the solid gain enough energy to overcome the strong forces holding them together, allowing them to slide past one another like a crowd of people moving out of an elevator door. | supported | The melting point of a solid is an indication of the strength of the force of attraction between its particles. |
| The heat energy absorbed by the solid does not raise its temperature during this phase change because it is used specifically to break these attractive bonds rather than increasing particle speed. | supported | The melting point of a solid is an indication of the strength of the force of attraction between its particles. |
| For example, ice melts at 0 degrees Celsius, meaning that once the water reaches this exact temperature, any additional heat will simply turn the ice into liquid without changing the temperature reading. | **unsupported** | The melting point of ice is 273.15 K |

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

> A combination reaction occurs when two or more different starting materials join together to create just one new product. This specific type of chemical change is defined by the fact that all reactants merge into a single substance, rather than breaking down into separate parts. For instance, when quick lime reacts with water, calcium oxide combines directly with liquid water to produce a single solid known as slaked lime, which follows this exact pattern of unity in the final result.
> 
> To understand why this happens, one must recognize that chemical reactions are fundamentally about rearranging atoms to form new bonds; if no other products are released, it indicates that the reactants have fully integrated into one compound. This concept is crucial because it helps students distinguish between complex processes where matter splits apart versus simpler ones where matter simply adds up together.
> 
> Everyday examples of this principle include rusting iron, where oxygen and iron combine to form a new substance called iron oxide, or cooking an egg, where heat causes the proteins in the egg white to bond into a single solid structure. By observing these scenarios, students can see how nature frequently builds complex structures from simpler ingredients without losing any material.
> 
> Think further by asking yourself: if you were to mix two different colored paints and they blended perfectly into one shade of color, would that be a combination reaction?

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| A combination reaction occurs when two or more different starting materials join together to create just one new product. | supported | In a combination reaction two or more substances combine to form a new single substance. |
| This specific type of chemical change is defined by the fact that all reactants merge into a single substance, rather than breaking down into separate parts. | supported | In a combination reaction two or more substances combine to form a new single substance. |
| For instance, when quick lime reacts with water, calcium oxide combines directly with liquid water to produce a single solid known as slaked lime, which follows this exact pattern of unity in the final result. | supported | In a combination reaction two or more substances combine to form a new single substance. |
| To understand why this happens, one must recognize that chemical reactions are fundamentally about rearranging atoms to form new bonds; if no other products are released, it indicates that the reactants have fully integrated into one compound. | supported | In a combination reaction two or more substances combine to form a new single substance. |
| This concept is crucial because it helps students distinguish between complex processes where matter splits apart versus simpler ones where matter simply adds up together. | supported | In a combination reaction two or more substances combine to form a new single substance. |
| Everyday examples of this principle include rusting iron, where oxygen and iron combine to form a new substance called iron oxide, or cooking an egg, where heat causes the proteins in the egg white to bond into a single solid structure. | supported | In a combination reaction two or more substances combine to form a new single substance. |
| By observing these scenarios, students can see how nature frequently builds complex structures from simpler ingredients without losing any material. | supported | In a combination reaction two or more substances combine to form a new single substance. |

*Not scored (1 sentence(s) asserting nothing):* question — Think further by asking yourself: if you were to mix two different colored paints and they blended perfectly into one shade of color, would that be a combination reaction?

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

> An exothermic reaction is a chemical process where heat energy is released into the surroundings as products are formed. This happens because the chemical bonds in the new substances form more weakly than the bonds holding the reactants together, causing the system to lose thermal energy. You can observe this effect clearly when you light a candle, as the flame heats up the surrounding air due to the heat generated by burning wax. A common example of such a reaction is the combustion of natural gas, which warms the room while producing carbon dioxide and water vapor. Think about how your body feels after eating a hot meal; that warmth comes from digestion reactions releasing excess energy into your environment.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| An exothermic reaction is a chemical process where heat energy is released into the surroundings as products are formed. | supported | In Activity 1.4, we also observed that a large amount of heat is evolved. This makes the reaction mixture warm. Reactions in which heat is released along with the formation of prod |
| This happens because the chemical bonds in the new substances form more weakly than the bonds holding the reactants together, causing the system to lose thermal energy. | **CONTRADICTED** | Reactions in which energy is absorbed are known as endothermic reactions. |
| You can observe this effect clearly when you light a candle, as the flame heats up the surrounding air due to the heat generated by burning wax. | **unsupported** | In Activity 1.4, we also observed that a large amount of heat is evolved. This makes the reaction mixture warm. Reactions in which heat is released along with the formation of prod |
| A common example of such a reaction is the combustion of natural gas, which warms the room while producing carbon dioxide and water vapor. | supported | In Activity 1.4, we also observed that a large amount of heat is evolved. This makes the reaction mixture warm. Reactions in which heat is released along with the formation of prod |

*Not scored (1 sentence(s) asserting nothing):* invitation — Think about how your body feels after eating a hot meal; that warmth comes from digestion reactions releasing excess energy into your environment.

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

> A displacement reaction occurs when one element replaces another element within a compound to form a new substance. This happens because the displaced element is more reactive than the one it was originally bonded to, causing a chemical exchange where atoms swap places. For instance, if you drop a piece of magnesium into copper sulfate solution, the magnesium will push the copper out of the solution and attach itself to the container instead.
> 
> This specific reaction is often written as an equation showing two different compounds turning into two entirely new ones, such as iron displacing copper from its compound. The textbook notes that in this process, a displacement reaction occurs when one element displaces another from its compound, resulting in a change of state for the substances involved. Students should remember that not all reactions involve elements swapping places; some simply break down into simpler parts or combine to form new materials without an exchange of positions between different chemical species.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| A displacement reaction occurs when one element replaces another element within a compound to form a new substance. | supported | When an element displaces another element from its compound, a displacement reaction occurs. |
| This happens because the displaced element is more reactive than the one it was originally bonded to, causing a chemical exchange where atoms swap places. | supported | When an element displaces another element from its compound, a displacement reaction occurs. |
| For instance, if you drop a piece of magnesium into copper sulfate solution, the magnesium will push the copper out of the solution and attach itself to the container instead. | supported | In this reaction, iron has displaced or removed another element, copper, from copper sulphate solution. This reaction is known as displacement reaction. |
| This specific reaction is often written as an equation showing two different compounds turning into two entirely new ones, such as iron displacing copper from its compound. | supported | Fe2O3 + 2Al → Al2O3 + 2Fe |
| The textbook notes that in this process, a displacement reaction occurs when one element displaces another from its compound, resulting in a change of state for the substances involved. | supported | When an element displaces another element from its compound, a displacement reaction occurs. |
| Students should remember that not all reactions involve elements swapping places; some simply break down into simpler parts or combine to form new materials without an exchange of positions between different chemical species. | supported | When an element displaces another element from its compound, a displacement reaction occurs. |

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

> A participial phrase is a group of words that starts with an -ing verb and describes something happening to or by another person or thing mentioned earlier in the story. These phrases add extra details about the main action, showing how it affects the subject without needing to repeat who is doing the action. For example, if someone is running fast, you can say they are "chasing after" a target instead of saying "someone is chasing after a target." This helps keep sentences shorter and more focused on the main idea.
> 
> Think about this when reading: whenever you see an -ing word like "singing," "laughing," or "flying," ask yourself what action is happening to the person being described. Understanding these phrases will help you read more fluently because you won't have to stop and guess who is doing what every single time.
> 
> Now that you understand how these phrases work, try reading a paragraph with many -ing verbs and see if you can spot them quickly without stopping to think about the specific actions involved.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| A participial phrase is a group of words that starts with an -ing verb and describes something happening to or by another person or thing mentioned earlier in the story. | supported | Participial phrases say something more about the person or thing talked about or the idea expressed by the sentence as a whole. |
| These phrases add extra details about the main action, showing how it affects the subject without needing to repeat who is doing the action. | supported | The parts in italics in the above sentences begin with -ing verbs, and are called participial phrases. Participial phrases say something more about the person or thing talked about |
| For example, if someone is running fast, you can say they are "chasing after" a target instead of saying "someone is chasing after a target." This helps keep sentences shorter and more focused on the main idea. | **unsupported** | Einstein became a gifted amateur violinist. He maintained this skill throughout his life. |
| Understanding these phrases will help you read more fluently because you won't have to stop and guess who is doing what every single time. | **unsupported** | Letters survive in which they put their affection into words, mixing science with tenderness. |
| Now that you understand how these phrases work, try reading a paragraph with many -ing verbs and see if you can spot them quickly without stopping to think about the specific actions involved. | **unsupported** | Now that you understand how these phrases work, try reading a paragraph with many -ing verbs and see if you can spot them quickly without stopping to think about the specific actio |

*Not scored (1 sentence(s) asserting nothing):* invitation — Think about this when reading: whenever you see an -ing word like "singing," "laughing," or "flying," ask yourself what action is happening to the person being described.

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

> A crop refers to all the plants grown on a large scale in a single place. These plants can be divided into different groups based on when they grow or what kind of food they provide. For instance, wheat is classified as a cereal because it is eaten as grain, while vegetables are grown for fresh consumption. This classification helps farmers choose the right plants for their specific region's climate. You might think of growing rice in one area and potatoes in another to match local conditions perfectly.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| A crop refers to all the plants grown on a large scale in a single place. | supported | 5. Certain plants of the same kind grown on a large scale. |
| These plants can be divided into different groups based on when they grow or what kind of food they provide. | supported | These can be classified on the basis of the season in which they grow. |
| For instance, wheat is classified as a cereal because it is eaten as grain, while vegetables are grown for fresh consumption. | supported | 5. Certain plants of the same kind grown on a large scale. |
| This classification helps farmers choose the right plants for their specific region's climate. | supported | 5. Certain plants of the same kind grown on a large scale. |
| You might think of growing rice in one area and potatoes in another to match local conditions perfectly. | supported | 5. Certain plants of the same kind grown on a large scale. |

**What the book answers with:** ✗ crops are classified by the season in which they grow

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

> An exothermic reaction is a chemical process where heat energy is released into the surroundings as products are formed. This happens because the bonds in the new substances form more tightly than the original ones, releasing stored energy. One common everyday example of this is burning natural gas, which warms up your kitchen while creating light and carbon dioxide.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| An exothermic reaction is a chemical process where heat energy is released into the surroundings as products are formed. | supported | In Activity 1.4, we also observed that a large amount of heat is evolved. This makes the reaction mixture warm. Reactions in which heat is released along with the formation of prod |
| This happens because the bonds in the new substances form more tightly than the original ones, releasing stored energy. | **unsupported** | In Activity 1.4, we also observed that a large amount of heat is evolved. This makes the reaction mixture warm. Reactions in which heat is released along with the formation of prod |
| One common everyday example of this is burning natural gas, which warms up your kitchen while creating light and carbon dioxide. | supported | Burning of natural gas |

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

