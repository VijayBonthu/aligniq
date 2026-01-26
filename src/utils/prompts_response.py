from pydantic import BaseModel, Field
from typing import Optional


class ProjectDefinition(BaseModel):
    title: str = Field(description="Title of the document")
    is_technical_document:bool = Field(description="True if the document is a technical document, False if it is an RFP")
    document_analysis: Optional[str] = Field(description="Analysis of the document type")
    project_statement: Optional[str] = Field(description="Project statement of the document type")
    technologies_provided: Optional[list[str]] = Field(description="Technologies provided in the document")
    team_roles: Optional[list[str]] = Field(description="Team roles provided in the document")
    project_scope: Optional[str] = Field(description="The project definition of the document")
    project_requirements: Optional[str] = Field(description= "Provides the project requirements")
    high_level_flow: Optional[str] = Field(description= "Provides the high level flow of the project from a system architect perspective")
    ambiguities: Optional[list[str]]= Field(description= "Provides the ambiguity analysis of the document")

    def to_markdown(self) -> str:
        """Convert the project definition to markdown"""

        title = self.title

        if not self.is_technical_document:
            md = f"#### Document Analysis\n{self.document_analysis}"
            return md, title
        
        md = f"## Project Statement\n{self.project_statement}\n\n"

        md += f"### Details provided\n"
        if self.technologies_provided:
            md += f"#### Technologies provided\n"
            for tech_details in self.technologies_provided:
                md+=f"- {tech_details}\n"
            md+= "\n"
        else:
            md += f"#### Technologies provided: None\n"

        if self.team_roles:
            md += f"#### Team Roles\n"
            for team_role in self.team_roles:
                md+=f"- {team_role}\n"
        else:
            md += f"#### Team Roles: None\n"

        if self.project_scope:
            md += f"### Project Scope\n{self.project_scope}\n\n"
        else:
            md += f"### Project Scope: None\n"
        
        if self.project_requirements:
            md += f"### Project Requirements\n{self.project_requirements}\n\n"
        else:
            md += f"### Project Requirements: None\n"

        if self.high_level_flow:
            md += f"### High Level Flow\n{self.high_level_flow}\n\n"
        else:
            md += f"### High Level Flow: None\n"

        if self.ambiguities:
            md += f"### Ambiguity Analysis\n"
            for ambiguity in self.ambiguities:
                md += f"- {ambiguity}\n"
        else:
            md += f"### Ambiguity Analysis: None\n"
        
        return md, title


class Chat_with_context(BaseModel):
    response: str = Field(description="response from LLM chat responding to user question regarding the document and its recommendations")

    def to_markdown(self) -> str:
        """Convert the chat_with_context to markdown"""
        md = ""
        for message in self.response:
            md += message
        return md

