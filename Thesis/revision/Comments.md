# July 2nd



#### (Abstract) The commonly accepted way of writing is with "We" form.

<img src="C:\Users\Probe\AppData\Roaming\Typora\typora-user-images\image-20260708200349498.png" alt="image-20260708200349498" style="zoom:67%;" />

#### (Introduction) What is a monitor? It is not explained

#### (Introduction) Both runtime monitoring and ROS2 need a bit more explanation.

<img src="C:\Users\Probe\AppData\Roaming\Typora\typora-user-images\image-20260708200535514.png" alt="image-20260708200535514" style="zoom:67%;" />

#### Do not state what was made in the prep phase.

Deleted

#### (Problem STatement) You first need to 

- explain why monitoring is needed in ROS2 applications. 
- Then indeed, the problem is that there are multiple configuration options and scenarios for monitoring: what to observe, how to observe, how to specify the properties, how to deploy the monitor, etc. 
- And all these choices have pros and cons. 
- There is a need for systematic specification of the monitoring solution. 
- Second, implementing it is often time consuming and needs to be automated. These are the main problem. 
- Only then you should say that you are not concerned with how properties are specified and checked.

<img src="C:\Users\Probe\AppData\Roaming\Typora\typora-user-images\image-20260708201023234.png" alt="image-20260708201023234" style="zoom:67%;" />

#### (1.3) validate -> evaluate

Fixed

#### (1.3) do not talk about plugins here, it is an implementation detail.

Fixed

#### (RQ2) I would reformulate this. What are the main features (or commonalities and variabilities) of the existing monitoring architectures? The feature diagram is just a way to depict them.

#### (RQ3) Instead of talking about chains and records, you can ask how a generic reference architecture for monitoring looks like and if it is capable of incorporating the features you identify in RQ2.

#### (RQ4) Reformulate this question entirely, the last question is usually about the evaluation of the approach.

![image-20260708201220286](C:\Users\Probe\AppData\Roaming\Typora\typora-user-images\image-20260708201220286.png)

#### (Summary after RQs) This paragraph needs to go to the next section.

Fixed

#### (1.4) Do not mention what you did in the prep phase. Explain for each research question what you are going to do

<img src="C:\Users\Probe\AppData\Roaming\Typora\typora-user-images\image-20260708202808289.png" alt="image-20260708202808289" style="zoom: 50%;" />

#### (1.5 Contributes) These need a reformulation. They are not clear to me.

<img src="C:\Users\Probe\AppData\Roaming\Typora\typora-user-images\image-20260708231359542.png" alt="image-20260708231359542" style="zoom:67%;" />

#### (Topics/Services/Actions) They are not introduced yet.

Fixed

#### (Background) Here you only explain ROS, not yet monitoring.

Fixed

#### (Background) Do not mix concepts from monitoring with the ROS explanation

Fixed

#### (2.1.3) I do not understand this paragraph

Separated observations (2.1) and how to monitor them (2.3)

#### (Topics/Services/Actions) For all three mechanisms you can show some diagrams

Diagrams added

<img src="C:\Users\Probe\AppData\Roaming\Typora\typora-user-images\image-20260708234001792.png" alt="image-20260708234001792" style="zoom:67%;" />

#### (Collecting data) or even instrument the code

<img src="C:\Users\Probe\AppData\Roaming\Typora\typora-user-images\image-20260709001257060.png" alt="image-20260709001257060" style="zoom:67%;" />

#### (For data records) may be talk more generally about data.

Use "event trace" instead of record, event trace was explained.



#### Here put a short explanation why you need this concept. I also expect an example feature diagram with the explanation of the notation.

(Now in Section 2.5)

<img src="C:\Users\Probe\AppData\Roaming\Typora\typora-user-images\image-20260709010230455.png" alt="image-20260709010230455" style="zoom:67%;" />

#### (2.6 Deployment and Transport) I expect somewhere to see different diagrams with the configuration. You can put them later in the chapter about deployment.

![image-20260709095424917](C:\Users\Probe\AppData\Roaming\Typora\typora-user-images\image-20260709095424917.png)

![image-20260709095433297](C:\Users\Probe\AppData\Roaming\Typora\typora-user-images\image-20260709095433297.png)