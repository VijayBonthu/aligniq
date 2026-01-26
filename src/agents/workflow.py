import json
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer,Image, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from datetime import datetime
from config import settings
import base64
from langchain.schema import HumanMessage, SystemMessage, AIMessage
from typing import List
from utils.logger import logger
import asyncio
from utils.prompts import Initial_phase, chat_with_context
from utils.prompts_response import ProjectDefinition, Chat_with_context

llm = ChatOpenAI(temperature=1, api_key=settings.OPENAI_CHATGPT, model="gpt-4o-mini")
# llm_vision = ChatOpenAI(temperature=1, api_key=settings.OPENAI_CHATGPT, model="gpt-4-vision-preview")

class ProjectScopingAgent:
    def __init__(self):
        self.requirements = []
        self.ambiguities = []
        self.tech_stack = []
        self.alternatives = []

    # def summarize_input(self, parsed_data:dict) -> dict:
    #     """Summarize the uploaded data capturing all the necessary developement of the product"""
    #     prompt = ChatPromptTemplate.from_template("""
    #     Analyse the data provided and create a comprehensive SUmmary of the project so that the downstream prompts can understand the application/problem they are trying to build/solve, techinical requirements provided, Constraints mentioned in the data, technologies expected to use, required time lines 
    # """)
        
    async def analyze_input(self, parsed_data: dict) -> dict:
        """Process parsed data to extract key requirements"""
        try:
            input_str = parsed_data["document"]
            logger.info(f"input_str: {input_str}")
            logger.info(f"type: {type(input_str)}")
            prompt = ChatPromptTemplate.from_template(Initial_phase)
            # prompt = ChatPromptTemplate.from_template("""
            # Analyze the project document and provide a comprehensive technical breakdown and the Teams and roles responsible for the project completion. 
            # Follow this structure STRICTLY:
            # **Input Analysis:**
            # {input}
            

            # *Response Format (JSON ONLY):**
            # {{
            # "project_definition": {{
            #     "aim": "<100-word concise statement>",
            #     "process flow":[
            #                     "For the given task, provide an end-to-end architecture with step-by-step details. For each step, specify:

            #                     What happens at this stage
            #                     The best technologies or tools to use
            #                     The exact engineering roles required (not broad categories, but specific positions such as Backend Engineer, Data Engineer, Cloud Engineer, etc.)
            #                     The number of people required for each role
            #                     The estimated time to complete this step
            #                     Format the response as follows:

            #                     Step 1: <Step Name>
            #                     Description: <Detailed explanation>
            #                     Technologies to Use: <List of specific technologies>
            #                     Roles Involved:
            #                     Frontend Engineer (1x) - Responsible for UI & integrations
            #                     Backend Engineer (2x) - API development & business logic
            #                     Cloud Engineer (1x) - Infrastructure setup & scaling
            #                     Estimated Time to Complete: <Time>
            #                     Step 2: <Step Name>
            #                     ..."]
            #     "scope": {{
            #     "included": ["list", "of", "scope", "items"],
            #     "excluded": ["out-of-scope", "elements"]
            #     }},
            #     "objectives": ["business", "technical", "objectives"],
            #     "pain_points": {{
            #     "explicit": ["client-stated", "pain", "points"],
            #     "inferred": ["AI-identified", "potential", "issues"]
            #     }}
            # }},

            # "technology_stack": {{
            #     "client_specified": {{
            #     "tools": ["requested", "technologies"],
            #     "implementation_strategy": "Approach to integrate these"
            #     }},
            #     "recommended_alternatives": [
            #     {{
            #         "tool": "Alternative Technology",
            #         "advantage": "Cost/Time/Performance Benefit",
            #         "migration_complexity": "Low/Medium/High"
            #     }}
            #     ]
            # }},
            # "risk_analysis": {{
            #     "technical_risks": ["potential", "technical", "challenges"],
            #     "mitigation_strategies": ["preventive", "measures"]
            # }}
            # }}

            # **Special Instructions:**
            # 1. For pain points: Identify 3-5 key issues even if not explicitly stated
            # 2. Team scaling: Use formula: developers_needed = base_count * (original_duration/compressed_duration)
            # 3. Alternatives: Prioritize COTS > Open Source > Custom Build
            # 4. Architecture: Include failover mechanisms and scalability considerations
            # 5. Risks: Highlight deadline-related risks specifically
            # """)
            
            
            chain = prompt | llm.with_structured_output(ProjectDefinition)
            response= await chain.ainvoke({"document": input_str})
            # response = await self._safe_json_parse(response)
            print(f"response: {response}")
            return response.to_markdown()
            # print(f"type: {type(response)}")
            # self.requirements.append(response)
            # return self.requirements[0]

        except Exception as e:
            logger.error(f"Error in analyze_input: {e}")
            raise

    async def identify_ambiguities(self):
        """Detect vague requirements needing clarification"""
        prompt = ChatPromptTemplate.from_template("""
        Identify ambiguities in these requirements and technicial challeges: {input}
        Generate follow-up questions to resolve them.
        Format: {{"questions": ["question1", "question2"]}}
        """)
        
        chain = prompt | llm | StrOutputParser()
        response = chain.invoke({"input": json.dumps(self.requirements)}) 
        print("RAW Ambiguity response:", response)
        self.ambiguities = self._safe_json_parse(response)
        return self.ambiguities

    async def generate_tech_recommendations(self): 
        """Suggest technology stacks with cost analysis"""
        prompt = ChatPromptTemplate.from_template("""
        Based on requirements: {input}
        Suggest:
        1. Primary tech stack (cloud + on-prem options)
        2. Alternatives with cost comparisons
        
        
        Format: {{
            "primary_stack": {{
                "cloud": ["tech1", "tech2"],
                "on_prem": ["tech3", "tech4"],
                "Optimized technologies to complete this project with cost efficiency": ["devops", "software technologies","Data science","AI"],
                "Developers required to complete this project": []
                                                  
            }},
            "alternatives": [
                {{
                    "type": "cloud",
                    "tech": ["alt_tech1"],
                    "cost_savings": ""
                }}
            ]
        }}
        """)
        
        chain = prompt | llm | StrOutputParser()
        response = chain.invoke({"input": json.dumps(self.requirements)})
        print("generate_tech_recommendations:", response)
        self.tech_stack = self._safe_json_parse(response)
        return self.tech_stack
    
    async def _safe_json_parse(self, json_str: str) -> dict:
        """Handle JSON parsing with error recovery"""
        try:
            # Remove markdown code blocks if present
            if asyncio.iscoroutine(json_str):
                json_str = await json_str
            cleaned = json_str.replace('```json', '').replace('```', '').strip()
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            print(f"Failed to parse JSON: {json_str}")
            print(f"Error: {e}")
            return {"error": "Invalid JSON response from LLM"}
        
    def generate_pdf_report(self, filename: str):
        """Create professional PDF document with formatted content"""
        # Custom Styles
        styles = getSampleStyleSheet()
        
        # Safe style modifications
        def safe_add_style(name, base_style=None, **kwargs):
            if name in styles:
                for key, value in kwargs.items():
                    setattr(styles[name], key, value)
            else:
                styles.add(ParagraphStyle(name, parent=base_style, **kwargs))
        
        safe_add_style('TitleCentered', base_style=styles['Title'],
                    alignment=1, textColor=colors.darkblue, fontName='Helvetica-Bold')
        safe_add_style('SectionHeader', base_style=styles['Heading2'],
                    fontSize=14, spaceAfter=12, textColor=colors.darkblue)
        styles['BodyText'].fontSize = 10
        styles['BodyText'].leading = 14

        # Create document template
        doc = SimpleDocTemplate(
            filename,
            pagesize=letter,
            leftMargin=0.5*inch,
            rightMargin=0.5*inch,
            topMargin=0.3*inch,
            bottomMargin=0.5*inch
        )
        
        flow = []
        
        # Header Section
        try:
            logo = Image("bird_2.jpg", width=2*inch, height=0.75*inch)
            header_table = Table([
                [logo, 
                Paragraph("Technical Proposal<br/>Project Scoping Document", styles['TitleCentered']),
                Paragraph("Confidential", styles['BodyText'])]
            ], colWidths=[2*inch, 4*inch, 1.5*inch])
            header_table.setStyle(TableStyle([
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('LINEBELOW', (0,0), (-1,-1), 1, colors.lightgrey)
            ]))
            flow.append(header_table)
        except:
            flow.append(Paragraph("Company Name", styles['TitleCentered']))
        
        flow.append(Spacer(1, 0.25*inch))
        
        # Project Overview
        flow.append(Paragraph("Project Overview", styles['SectionHeader']))
        overview_data = [
            ["Client Name:", "Acme Corporation"],
            ["Date Prepared:", datetime.today().strftime('%Y-%m-%d')]
        ]
        overview_table = Table(overview_data, colWidths=[1.5*inch, 4*inch])
        overview_table.setStyle(TableStyle([
            ('FONTNAME', (0,0), (-1,-1), 'Helvetica-Bold'),
            ('BACKGROUND', (0,0), (-1,0), colors.lightblue)
        ]))
        flow.append(overview_table)
        
        # Project Definition Section
        flow.append(PageBreak())
        flow.append(Paragraph("Project Definition", styles['SectionHeader']))
        
        def format_dict(data, indent=0):
            """Recursively format dictionary data for PDF"""
            formatted = []
            for key, value in data.items():
                key_str = f"<b>{key.replace('_', ' ').title()}:</b>"
                if isinstance(value, dict):
                    formatted.append(Paragraph(key_str, styles['BodyText']))
                    formatted += format_dict(value, indent+1)
                elif isinstance(value, list):
                    formatted.append(Paragraph(key_str, styles['BodyText']))
                    for item in value:
                        formatted.append(Paragraph(f"• {item}", styles['BodyText']))
                else:
                    text = f"{key_str} {value}"
                    formatted.append(Paragraph(text, styles['BodyText']))
            return formatted
        
        # Add formatted requirements
        if isinstance(self.requirements, dict):
            flow += format_dict(self.requirements.get('project_definition', {}))
            flow += format_dict(self.requirements.get('technology_stack', {}))
            flow += format_dict(self.requirements.get('risk_analysis', {}))
        else:
            flow.append(Paragraph("No requirements data available", styles['BodyText']))
        
        # System Design Section
        def wrapped_text(content, width, style):
            return Paragraph(f"<para fontSize={style.fontSize} leading={style.leading}>\
                            {content}</para>", style)

        # System Design Section
        flow.append(PageBreak())
        flow.append(Paragraph("System Design", styles['SectionHeader']))

        # Technology Stack Section
        flow.append(Spacer(1, 0.25*inch))
        flow.append(Paragraph("Technology Stack", styles['SectionHeader']))
        
        if isinstance(self.tech_stack, dict):
            # Prepare table data with dynamic content
            tech_data = [
                ["<b>Type</b>", "<b>Technologies</b>", "<b>Details</b>"]
            ]
            
            # Primary Cloud Stack
            tech_data.append([
                "Primary (Cloud)",
                wrapped_text("<br/>• " + "<br/>• ".join(
                    self.tech_stack.get('primary_stack', {}).get('cloud', [])
                ), 2*inch, styles['BodyText']),
                wrapped_text(
                    self.tech_stack.get('primary_stack', {}).get('Optimized technologies to complete this project with cost efficiency', ""), 
                    2.5*inch, styles['BodyText']
                ),
                wrapped_text(
                    self.tech_stack.get('primary_stack', {}).get('Developers required to complete this project', ""), 
                    2.5*inch, styles['BodyText']
                )
            ])
            
            # Primary On-Prem Stack
            tech_data.append([
                "Primary (On-Prem)",
                wrapped_text("<br/>• " + "<br/>• ".join(
                    self.tech_stack.get('primary_stack', {}).get('on_prem', [])
                ), 2*inch, styles['BodyText']),
                ""
            ])
            
            # Alternatives
            alternatives = [
                f"{alt['tech'][0]} ({alt['cost_savings']})" 
                for alt in self.tech_stack.get('alternatives', [])
            ]
            tech_data.append([
                "Alternatives",
                wrapped_text("<br/>• " + "<br/>• ".join(alternatives), 2*inch, styles['BodyText']),
                ""
            ])
            
            # Create table with dynamic sizing
            tech_table = Table(tech_data, colWidths=[1.5*inch, 2*inch, 2.5*inch])
            tech_table.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.lightblue),
                ('GRID', (0,0), (-1,-1), 0.5, colors.lightgrey),
                ('VALIGN', (0,0), (-1,-1), 'TOP'),
                ('WORDWRAP', (0,0), (-1,-1)),
                ('LEADING', (0,0), (-1,-1), 14),
                ('FONTSIZE', (0,0), (-1,-1), 10)
            ]))
            
            # Auto-size rows
                # **Dynamically Adjust Table Size**
            max_width = doc.width  # Get max width available in document
            max_height = doc.height  # Get max height available

            # **Calculate Required Width & Height**
            table_width, table_height = tech_table.wrapOn(None, max_width, max_height)

            # **Ensure the Table Fits the Page**
            table_width = min(table_width, max_width)
            table_height = min(table_height, max_height)
                        
            flow.append(tech_table)
            flow.append(Spacer(1, 0.25*inch))
        
        # Ambiguities Section
        flow.append(PageBreak())
        flow.append(Paragraph("Open Questions", styles['SectionHeader']))
        if isinstance(self.ambiguities, dict) and 'questions' in self.ambiguities:
            for i, question in enumerate(self.ambiguities['questions'], 1):
                flow.append(Paragraph(f"{i}. {question}", styles['BodyText']))
        
        # Footer with Page Numbers
        def add_page_numbers(canvas, doc):
            canvas.saveState()
            canvas.setFont('Helvetica', 8)
            canvas.drawCentredString(4.25*inch, 0.5*inch, f"Page {doc.page}")
            canvas.restoreState()
        
        doc.build(flow, onFirstPage=add_page_numbers, onLaterPages=add_page_numbers)

    @staticmethod
    async def summarize_image(image_path: str, max_tokens=1000):
        """
        Generate a detailed summary of an image using GPT-4 Vision.
        
        Args:
            image_path (str): Path to the image file or URL.
            max_tokens (int): Maximum length of the response.
        """
        # Encode image if it's a local file
        if image_path.startswith(("http://", "https://")):
            # For URLs
            image_url = image_path
        else:
            # For local files
            with open(image_path, "rb") as image_file:
                base64_image = base64.b64encode(image_file.read()).decode("utf-8")
            image_url = f"data:image/jpeg;base64,{base64_image}"

        message = [
        SystemMessage(content="""
        You are a technical expert. Analyze the provided image in detail. 
        If it's a software architecture diagram, explain all components, connections, 
        data flows, and technologies. Highlight key design patterns or potential issues.
        """),
        HumanMessage(content=[
            {"type": "text", "text": """Explain this image comprehensively. Include every important detail, 
        such as text labels, symbols, relationships, and overall structure."""},
            {"type": "image_url", "image_url": {"url": image_url}},
        ])
    ]

        # Send request to GPT-4 Vision
        response = llm.invoke(message)
        logger.info(f"response from summarize_image: {response}")
            
        return response.content
    
    @staticmethod
    async def chat_with_doc(context:List[dict]):
        prompt = ChatPromptTemplate.from_template(chat_with_context)
        user_latest_chat = context[-1]['content']
        chain = prompt | llm.with_structured_output(Chat_with_context)
        logger.info(f"chat_context: {context}")
        logger.info(f"type of context: {type(context)}")
        logger.info(f"type of context[0]: {chain}")
        response = await chain.ainvoke({"chat_context": context[:-1], "user_chat": user_latest_chat})
        return {"message": response.to_markdown()}
