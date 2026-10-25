"""Synthetic outward originals and independent reviewed book rows."""

async def prepare(client, headers, engagement, reviewer):
    from tests.qa_crud.test_country_workflows import decision, source
    from tests.qa_crud.test_india_gstr1_source import retained
    from tests.unit.test_india_gstr1_source import GSTIN, books, controls

    base=f"/api/v1/engagements/{engagement}/audit"
    _, originals=await retained(client,headers,engagement,base)
    book=await source(client,headers,engagement,books()["rows"],"SYNTHETIC outward sales register","tax-documents",{"INR":"18"})
    reviewed=await decision(client,reviewer[0],engagement,book)
    assert reviewed.status_code==201,reviewed.text
    return {"books":reviewed.json()["id"],"original":originals[0][1]["id"],"context":originals[1][1]["id"],"controls":controls(),"gstin":GSTIN}
