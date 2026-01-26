from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage, AIMessage
from rich.console import Console
from rich.markdown import Markdown

class AccessLLM:
    def __init__(self, api_key:str=None):
        self.api_key = api_key
        self.client = ChatOpenAI(temperature=1, api_key=self.api_key, model="gpt-4o-mini")
        self.last_prompt = None
        self.last_response = None

    def send_chat(self, user_message:str=None, list_of_developers:list = [None], expected_time:int=None):
        self.user_message = user_message
        self.list_of_developers = list_of_developers
        self.expected_time = expected_time
        response = self.client.invoke(
            [
                SystemMessage(content="""You are an AI assistant specialized in helping technical sales teams and business analysts estimate the time required to complete an MVP or entire project based on client requirements. The Business Analysts or Technical Team will provide you with the client's requirement document and a list of available developers or team members for the project. Your task is to estimate the time needed to complete the project, if expected time is provided use that for the reference and complete the project within that time frame with the provided team, and generate additional questions that can clarify the requirements and provide more context for the developers or architects.
                                2. **List of Tasks/Steps**:
                                    - Break down the project into key tasks or steps.
                                    - Provide a brief description of what each task involves.
                                    - Include the number of members and their roles required to complete each task.
                                    - Estimate the time needed for each task and time allocation per team member, if applicable.
                                3. **Ambiguity in Requirements**:
                                - Identify potential ambiguities in the client's requirements.
                                - Provide questions to clarify these ambiguities, with examples for each questions to help guide the business analyst or technical sales team.
                                4. **Use the Constraints provided by the user

                                Do not include any conclusions, summaries, or final remarks in the response. Focus solely on providing the necessary details for developers and architects to proceed with clarity. consise the response to 3000 tokens"""
                              
                              ),
                              HumanMessage(content=f"""Hello"""
                                            )
                # HumanMessage(content=f"""Techinical documentation: {self.user_message}
                #                         Constraints: 
                #                             - list_of_developer: {self.list_of_developers}
                #                             - expected time to complete the entire project: {self.expected_time}"""
                #                             )
            ]
        )

        self.last_prompt = f"{SystemMessage:}\n\n{HumanMessage}"



        print(self.last_prompt)

        return response


    def display_text(self,text_dict):
        console = Console()
        content = text_dict.get("content", "")
        
        # Use Markdown to format and display the text
        md = Markdown(content)
        console.print(md)

        return md

